import asyncio
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv
import httpx
from app.logging_config import get_logger

load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Публичный URL (для web_app ссылок)
PUBLIC_WEBAPP_URL = os.getenv("PUBLIC_WEBAPP_URL", os.getenv("WEBAPP_URL", "http://localhost:8000"))
# Внутренний URL API (для http-запросов из docker-сети)
INTERNAL_API_URL = os.getenv("INTERNAL_API_URL", os.getenv("WEBAPP_URL", "http://localhost:8000"))
SUPER_ADMIN_IDS = {int(x) for x in os.getenv("SUPER_ADMIN_IDS", "").split(",") if x.strip().isdigit()}
ADMIN_CODE = os.getenv("ADMIN_CODE", "").strip()

# Простая сессия для авторизованных по кодовому слову
ADMIN_SESSIONS: set[int] = set()


logger = get_logger("tg-bot")
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: types.Message) -> None:
    # register user as active and save username
    username = message.from_user.username
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Активируем пользователя и сохраняем username
            r = await client.post(
                INTERNAL_API_URL + "/api/users/activate", 
                headers={"X-Telegram-User-Id": str(message.from_user.id)},
                json={"username": username} if username else {}
            )
            logger.info("activate_user id=%s username=%s status=%s", message.from_user.id, username, getattr(r, "status_code", "n/a"))
    except Exception as exc:
        logger.exception("activate_user failed: %s", repr(exc))
        # Продолжаем выполнение даже если активация не удалась
    
    url = PUBLIC_WEBAPP_URL + f"/static/index.html?ngrok-skip-browser-warning=1&uid={message.from_user.id}&v=6"
    if PUBLIC_WEBAPP_URL.lower().startswith("https://"):
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=url))]]
        )
        await message.answer("Добро пожаловать! Откройте mini app.", reply_markup=kb)
    else:
        await message.answer(
            "Для открытия mini app нужен HTTPS. Временно откройте по ссылке: " + url
        )


async def _is_restaurant_admin(user_id: int) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url = INTERNAL_API_URL + "/api/ra/me"
            r = await client.get(url, headers={"X-Telegram-User-Id": str(user_id)})
            return r.status_code == 200
    except Exception:
        return False


def _inline_kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for (t, d) in row] for row in rows]
    )

RA_INLINE_KB = _inline_kb([
    [("Профиль ресторана", "ra_profile"), ("Меню", "open_menu")],
])


@dp.message(Command("status"))
async def check_user_status(message: types.Message) -> None:
    """Команда для проверки статуса пользователя"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    response = f"👤 **Статус пользователя:**\n\n"
    response += f"**ID:** `{user_id}`\n"
    if username:
        response += f"**Username:** @{username}\n"
    if first_name:
        response += f"**Имя:** {first_name}\n"
    
    # Проверяем, является ли пользователь админом ресторана
    is_ra = await _is_restaurant_admin(user_id)
    response += f"\n**Админ ресторана:** {'✅ Да' if is_ra else '❌ Нет'}"
    
    # Проверяем, является ли пользователь главным админом
    is_super = user_id in SUPER_ADMIN_IDS
    response += f"\n**Главный админ:** {'✅ Да' if is_super else '❌ Нет'}"
    
    if not is_ra and not is_super:
        response += f"\n\n💡 **Для получения прав используйте:**\n"
        response += f"• `/id` - получить ваш ID\n"
        response += f"• Обратитесь к главному администратору"
    
    await message.answer(response, parse_mode="Markdown")


@dp.message(Command("id"))
async def get_user_id(message: types.Message) -> None:
    """Команда для получения ID пользователя"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    response = f"🆔 **Информация о пользователе:**\n\n"
    response += f"**ID:** `{user_id}`\n"
    if username:
        response += f"**Username:** @{username}\n"
    if first_name:
        response += f"**Имя:** {first_name}\n"
    
    response += f"\n💡 **Для назначения админом ресторана используйте ID:** `{user_id}`"
    
    await message.answer(response, parse_mode="Markdown")

@dp.message(Command("admin"))
async def admin_entry(message: types.Message) -> None:
    user_id = message.from_user.id
    # Если пользователь — админ ресторана, показываем кнопки профиля ресторана
    if await _is_restaurant_admin(user_id):
        await message.answer("Доступ к профилю ресторана открыт.", reply_markup=RA_INLINE_KB)
        return
    
    # Если пользователь не админ ресторана, предлагаем стать им
    await message.answer(
        "У вас нет доступа к админке ресторана.\n\n"
        "Чтобы стать админом ресторана:\n"
        "1. Попросите главного администратора добавить вас как админа ресторана\n"
        "2. Или используйте команду /id чтобы получить ваш ID для назначения\n\n"
        "Если вы уже должны быть админом, проверьте правильность настройки."
    )


# --- Главная админка через кодовое слово и кнопки ---



# Inline кнопки меню главного админа
ADMIN_INLINE_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Добавить ресторан", callback_data="admin_add_restaurant"),
            InlineKeyboardButton(text="Удалить ресторан", callback_data="admin_delete_restaurant")
        ],
        [
            InlineKeyboardButton(text="Включить ресторан", callback_data="admin_enable_restaurant"),
            InlineKeyboardButton(text="Выключить ресторан", callback_data="admin_disable_restaurant")
        ],
        [
            InlineKeyboardButton(text="Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="Статистика", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton(text="Веб-админка", callback_data="admin_web")
        ],
        [
            InlineKeyboardButton(text="Меню", callback_data="admin_menu")
        ],
    ]
)

# Клавиатуры для статистики
STATS_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Общая статистика", callback_data="stats_global"),
            InlineKeyboardButton(text="Статистика по ресторану", callback_data="stats_restaurant")
        ],
        [
            InlineKeyboardButton(text="Статистика пользователей", callback_data="stats_users")
        ],
        [
            InlineKeyboardButton(text="← Назад", callback_data="admin_back")
        ],
    ]
)


@dp.message(lambda message: message.text and os.getenv("ADMIN_CODE", "").strip() and message.text.strip() == os.getenv("ADMIN_CODE", "").strip())
async def handle_admin_code(message: types.Message) -> None:
    # Вход в главную админку по кодовому слову
    ADMIN_SESSIONS.add(message.from_user.id)
    await message.answer("Код принят. Доступ в админку открыт.", reply_markup=ADMIN_INLINE_KB)





# --- Главный админ: Добавить/Удалить ресторан ---

ADD_REST_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="@Имя аккаунта"), KeyboardButton(text="Название ресторана")], [KeyboardButton(text="Отмена")]],
    resize_keyboard=True,
)

DEL_REST_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Отмена")]],
    resize_keyboard=True,
)

CONFIRM_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]], resize_keyboard=True
)

ADD_FLOW: dict[int, dict] = {}
BROADCAST_FLOW: dict[int, dict] = {}
DEL_FLOW: dict[int, dict] = {}


async def _resolve_user_id_by_username(username: str) -> int | None:
    uname = username.strip()
    if not uname:
        return None
    if not uname.startswith("@"):
        uname = "@" + uname
    if not BOT_TOKEN:
        return None
    
    print(f"DEBUG: Resolving username: {uname}")
    
    try:
        async with httpx.AsyncClient(timeout=7) as client:
            # Сначала пробуем getChat
            resp = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getChat", params={"chat_id": uname})
            data = resp.json()
            print(f"DEBUG: getChat response: {data}")
            
            if data.get("ok") and data.get("result", {}).get("id"):
                user_id = int(data["result"]["id"])
                print(f"DEBUG: Found user_id via getChat: {user_id}")
                return user_id
            
            # Если getChat не сработал, пробуем через API нашего приложения
            print(f"DEBUG: getChat failed, trying internal API")
            api_resp = await client.get(f"{INTERNAL_API_URL}/api/admin/users/resolve-username?username={uname}")
            api_data = api_resp.json()
            print(f"DEBUG: Internal API response: {api_data}")
            
            if api_resp.status_code == 200 and api_data.get("user_id"):
                user_id = int(api_data["user_id"])
                print(f"DEBUG: Found user_id via internal API: {user_id}")
                return user_id
                
    except Exception as e:
        print(f"DEBUG: Exception in _resolve_user_id_by_username: {e}")
        return None
    
    print(f"DEBUG: Could not resolve username: {uname}")
    return None


# Обработчики Inline кнопок админки
@dp.callback_query(F.data == "admin_add_restaurant")
async def admin_add_restaurant_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    print(f"DEBUG: admin_add_restaurant_callback called for user {uid}")
    
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к операции добавления ресторана.")
        return
    
    # Инициализируем процесс добавления ресторана
    ADD_FLOW[uid] = {"username": None, "name": None, "step": "username"}
    print(f"DEBUG: ADD_FLOW initialized for user {uid}: {ADD_FLOW[uid]}")
    
    await callback.message.answer("Введите username админа в формате @username или ID пользователя")
    await callback.answer()

@dp.callback_query(F.data == "admin_delete_restaurant")
async def admin_delete_restaurant_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к операции удаления ресторана.")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(INTERNAL_API_URL + "/api/admin/restaurants", headers={"X-Telegram-User-Id": str(uid)})
            if response.status_code == 200:
                restaurants = response.json()
                
                if not restaurants:
                    await callback.message.answer("❌ Нет ресторанов для удаления.")
                    return
                
                # Создаем клавиатуру со списком ресторанов
                keyboard = []
                for restaurant in restaurants:
                    status = "✅" if restaurant.get("is_enabled") else "❌"
                    keyboard.append([
                        InlineKeyboardButton(
                            text=f"{status} {restaurant['name']}", 
                            callback_data=f"delete_rest_{restaurant['id']}"
                        )
                    ])
                
                keyboard.append([InlineKeyboardButton(text="← Назад", callback_data="admin_back")])
                
                kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
                await callback.message.edit_text("🗑️ Выберите ресторан для удаления:", reply_markup=kb)
            else:
                await callback.message.answer("❌ Ошибка получения списка ресторанов")
    except Exception as e:
        logger.exception("Error getting restaurants for delete")
        await callback.message.answer("❌ Ошибка получения списка ресторанов")
    
    await callback.answer()

@dp.callback_query(F.data == "admin_enable_restaurant")
async def admin_enable_restaurant_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к операции включения ресторана.")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(INTERNAL_API_URL + "/api/admin/restaurants", headers={"X-Telegram-User-Id": str(uid)})
            if response.status_code == 200:
                restaurants = response.json()
                disabled_restaurants = [r for r in restaurants if not r.get("is_enabled")]
                
                if not disabled_restaurants:
                    await callback.message.answer("❌ Нет выключенных ресторанов для включения.")
                    return
                
                # Создаем клавиатуру со списком выключенных ресторанов
                keyboard = []
                for restaurant in disabled_restaurants:
                    keyboard.append([
                        InlineKeyboardButton(
                            text=f"✅ {restaurant['name']}", 
                            callback_data=f"enable_rest_{restaurant['id']}"
                        )
                    ])
                
                keyboard.append([InlineKeyboardButton(text="← Назад", callback_data="admin_back")])
                
                kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
                await callback.message.edit_text("🔓 Выберите ресторан для включения:", reply_markup=kb)
            else:
                await callback.message.answer("❌ Ошибка получения списка ресторанов")
    except Exception as e:
        logger.exception("Error getting restaurants for enable")
        await callback.message.answer("❌ Ошибка получения списка ресторанов")
    
    await callback.answer()

@dp.callback_query(F.data == "admin_disable_restaurant")
async def admin_disable_restaurant_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к операции выключения ресторана.")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(INTERNAL_API_URL + "/api/admin/restaurants", headers={"X-Telegram-User-Id": str(uid)})
            if response.status_code == 200:
                restaurants = response.json()
                enabled_restaurants = [r for r in restaurants if r.get("is_enabled")]
                
                if not enabled_restaurants:
                    await callback.message.answer("❌ Нет включенных ресторанов для выключения.")
                    return
                
                # Создаем клавиатуру со списком включенных ресторанов
                keyboard = []
                for restaurant in enabled_restaurants:
                    keyboard.append([
                        InlineKeyboardButton(
                            text=f"❌ {restaurant['name']}", 
                            callback_data=f"disable_rest_{restaurant['id']}"
                        )
                    ])
                
                keyboard.append([InlineKeyboardButton(text="← Назад", callback_data="admin_back")])
                
                kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
                await callback.message.edit_text("🔒 Выберите ресторан для выключения:", reply_markup=kb)
            else:
                await callback.message.answer("❌ Ошибка получения списка ресторанов")
    except Exception as e:
        logger.exception("Error getting restaurants for disable")
        await callback.message.answer("❌ Ошибка получения списка ресторанов")
    
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к рассылке.")
        return
    
    # Создаем клавиатуру для выбора типа получателей
    target_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Всем пользователям", callback_data="broadcast_all"),
                InlineKeyboardButton(text="🛒 Только клиентам", callback_data="broadcast_clients")
            ],
            [
                InlineKeyboardButton(text="🏪 Только ресторанам", callback_data="broadcast_restaurants")
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")
            ]
        ]
    )
    
    await callback.message.answer(
        "📢 <b>Рассылка</b>\n\n"
        "Выберите, кому отправить сообщение:",
        reply_markup=target_kb,
        parse_mode="HTML"
    )
    await callback.answer()


# ===========================================
# ОБРАБОТЧИКИ АДМИНКИ РЕСТОРАНА (ДОЛЖНЫ БЫТЬ ПЕРЕД ОБРАБОТЧИКАМИ РАССЫЛКИ)
# ===========================================

@dp.callback_query(F.data == "ra_profile")
async def open_ra_profile(cb: types.CallbackQuery) -> None:
    message = cb.message
    user_id = cb.from_user.id  # Используем cb.from_user.id вместо message.from_user.id
    if not await _is_restaurant_admin(user_id):
        await cb.answer("Нет доступа", show_alert=True)
        return
    if not PUBLIC_WEBAPP_URL.lower().startswith("https://"):
        url = PUBLIC_WEBAPP_URL + f"/static/ra_profile.html?uid={user_id}&ngrok-skip-browser-warning=1"
        await cb.message.answer("Временно откройте по ссылке: " + url)
        return
    url = PUBLIC_WEBAPP_URL + f"/static/ra_profile.html?uid={user_id}&ngrok-skip-browser-warning=1"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть профиль ресторана", web_app=WebAppInfo(url=url))]])
    await cb.message.answer("Профиль ресторана", reply_markup=kb)
    await cb.answer()

# ===========================================
# ОБРАБОТЧИКИ РАССЫЛКИ
# ===========================================

@dp.callback_query(F.data.in_(["broadcast_all", "broadcast_clients", "broadcast_restaurants"]))
async def broadcast_target_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к рассылке.")
        return
    
    target_type = callback.data.replace("broadcast_", "")
    
    # Инициализируем состояние рассылки
    # Очищаем PENDING_INPUT и ADD_FLOW, чтобы избежать конфликтов
    PENDING_INPUT.pop(uid, None)
    ADD_FLOW.pop(uid, None)
    
    BROADCAST_FLOW[uid] = {
        "target_type": target_type,
        "text": None,
        "media_type": None,
        "media_file_id": None,
        "step": "text"
    }
    
    target_names = {
        "all": "всем пользователям",
        "clients": "только клиентам", 
        "restaurants": "только ресторанам"
    }
    
    await callback.message.answer(
        f"📝 <b>Введите текст сообщения</b>\n\n"
        f"Получатели: {target_names[target_type]}\n\n"
        f"💡 <i>Вы также можете отправить фото или видео с подписью</i>\n\n"
        f"Для отмены напишите: <code>отмена</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_web")
async def admin_web_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    token = None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(INTERNAL_API_URL + "/api/auth/external-link", timeout=5)
            token = r.json().get("token") if r.status_code == 200 else None
    except Exception:
        token = None
    url = PUBLIC_WEBAPP_URL + f"/static/admin.html?uid={uid}&ngrok-skip-browser-warning=1&v=5"
    if token:
        url += f"&token={token}"
    await callback.message.answer(f"Веб-админка: {url}")
    await callback.answer()

@dp.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к меню.")
        return
    await callback.message.answer("Меню админки:", reply_markup=ADMIN_INLINE_KB)
    await callback.answer()

# Старые обработчики для совместимости
@dp.message(F.text == "Добавить ресторан")
async def ga_add_restaurant(message: types.Message) -> None:
    uid = message.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await message.answer("Нет доступа к операции добавления ресторана.")
        return
    ADD_FLOW[uid] = {"username": None, "name": None}
    await message.answer("Укажите данные для нового ресторана:", reply_markup=ADD_REST_KB)


@dp.message(F.text == "@Имя аккаунта")
async def ga_ask_username(message: types.Message) -> None:
    uid = message.from_user.id
    if uid not in SUPER_ADMIN_IDS or uid not in ADD_FLOW:
        return
    PENDING_INPUT[uid] = {"kind": "ga_add_username"}
    await message.answer("Введите @username аккаунта ресторатора (пример: @user)")


@dp.message(F.text == "Название ресторана")
async def ga_ask_rest_name(message: types.Message) -> None:
    uid = message.from_user.id
    if uid not in SUPER_ADMIN_IDS or uid not in ADD_FLOW:
        return
    PENDING_INPUT[uid] = {"kind": "ga_add_name"}
    await message.answer("Введите название ресторана")


async def _try_finish_add_restaurant(uid: int, message: types.Message) -> None:
    state = ADD_FLOW.get(uid)
    if not state or not state.get("username") or not state.get("name"):
        return
    # resolve user id
    admin_user_id = await _resolve_user_id_by_username(state["username"])
    if not admin_user_id:
        await message.answer("Не удалось определить аккаунт по username. Проверьте написание и попробуйте снова.")
        return
    # create restaurant (disabled by default)
    try:
        async with httpx.AsyncClient(timeout=7) as client:
            r = await client.post(PUBLIC_WEBAPP_URL + "/api/admin/restaurants", json={"name": state["name"]}, headers={"X-Telegram-User-Id": str(uid)})
            if r.status_code != 200:
                await message.answer("Ошибка создания ресторана.")
                return
            new_id = (r.json() or {}).get("id")
            if not new_id:
                await message.answer("Не удалось получить id нового ресторана.")
                return
            # bind admin
            await client.post(PUBLIC_WEBAPP_URL + f"/api/admin/users/bind-admin?user_id={admin_user_id}&restaurant_id={new_id}", headers={"X-Telegram-User-Id": str(uid)})
        await message.answer(f"Ресторан \"{state['name']}\" добавлен.", reply_markup=ADMIN_INLINE_KB)
        ADD_FLOW.pop(uid, None)
    except Exception:
        await message.answer("Сбой при добавлении ресторана. Попробуйте снова.")


@dp.message(F.text == "Отмена")
async def ga_cancel(message: types.Message) -> None:
    uid = message.from_user.id
    ADD_FLOW.pop(uid, None)
    DEL_FLOW.pop(uid, None)
    PENDING_INPUT.pop(uid, None)
    await message.answer("Действие отменено.", reply_markup=ADMIN_INLINE_KB)


# Обработчик для отмены добавления ресторана
@dp.message(lambda message: message.text.lower() == "отмена" and message.from_user.id in ADD_FLOW)
async def cancel_add_restaurant(message: types.Message) -> None:
    uid = message.from_user.id
    
    # Не обрабатываем, если пользователь в состоянии рассылки
    if uid in BROADCAST_FLOW:
        print(f"DEBUG: User {uid} in BROADCAST_FLOW, skipping ADD_FLOW cancel handler")
        return
    
    if uid in ADD_FLOW:
        ADD_FLOW.pop(uid, None)
        await message.answer("❌ Добавление ресторана отменено.")


# Обработчик для диалога добавления ресторана
@dp.message(lambda message: message.from_user.id in ADD_FLOW and ADD_FLOW[message.from_user.id].get("step") == "username" and message.text and (message.text.startswith("@") or message.text.isdigit()))
async def handle_add_restaurant_username(message: types.Message) -> None:
    uid = message.from_user.id
    
    # Не обрабатываем, если пользователь в состоянии рассылки
    if uid in BROADCAST_FLOW:
        print(f"DEBUG: User {uid} in BROADCAST_FLOW, skipping restaurant username handler")
        return
    
    print(f"DEBUG: Username handler triggered for user {uid}, text: {message.text}")
    
    state = ADD_FLOW[uid]
    input_text = message.text.strip()
    
    admin_user_id = None
    
    # Если введен ID пользователя
    if input_text.isdigit():
        admin_user_id = int(input_text)
        print(f"DEBUG: Using direct user_id: {admin_user_id}")
    else:
        # Если введен username
        admin_user_id = await _resolve_user_id_by_username(input_text)
        if not admin_user_id:
            await message.answer("❌ Не удалось найти пользователя с таким username. Проверьте написание и попробуйте снова.\n\n💡 Подсказка: Пользователь должен сначала взаимодействовать с ботом (написать /start), чтобы его можно было найти по username.")
            return
    
    # Сохраняем username/ID и переходим к следующему шагу
    state["username"] = input_text
    state["admin_user_id"] = admin_user_id  # Сохраняем ID для использования позже
    state["step"] = "name"
    await message.answer("Введите название ресторана")

@dp.message(lambda message: message.from_user.id in ADD_FLOW and ADD_FLOW[message.from_user.id].get("step") == "name")
async def handle_add_restaurant_name(message: types.Message) -> None:
    uid = message.from_user.id
    
    # Не обрабатываем, если пользователь в состоянии рассылки
    if uid in BROADCAST_FLOW:
        print(f"DEBUG: User {uid} in BROADCAST_FLOW, skipping restaurant name handler")
        return
    
    print(f"DEBUG: Restaurant name handler triggered for user {uid}, text: {message.text}")
    
    state = ADD_FLOW[uid]
    
    # Обрабатываем ввод названия ресторана
    restaurant_name = message.text.strip()
    if not restaurant_name:
        await message.answer("❌ Название ресторана не может быть пустым. Попробуйте снова.")
        return
    
    # Сохраняем название и создаем ресторан
    state["name"] = restaurant_name
    
    # Создаем ресторан
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Создаем ресторан
            create_response = await client.post(
                INTERNAL_API_URL + "/api/admin/restaurants",
                json={"name": restaurant_name},
                headers={"X-Telegram-User-Id": str(uid)}
            )
            
            if create_response.status_code != 200:
                await message.answer("❌ Ошибка создания ресторана.")
                ADD_FLOW.pop(uid, None)
                return
            
            new_restaurant = create_response.json()
            new_id = new_restaurant.get("id")
            
            if not new_id:
                await message.answer("❌ Не удалось получить ID нового ресторана.")
                ADD_FLOW.pop(uid, None)
                return
            
            # Назначаем админа
            admin_user_id = state.get("admin_user_id")
            if not admin_user_id:
                await message.answer("❌ Ошибка: не найден ID админа.")
                ADD_FLOW.pop(uid, None)
                return
            bind_response = await client.post(
                INTERNAL_API_URL + f"/api/admin/users/bind-admin?user_id={admin_user_id}&restaurant_id={new_id}",
                headers={"X-Telegram-User-Id": str(uid)}
            )
            
            if bind_response.status_code != 200:
                await message.answer("⚠️ Ресторан создан, но не удалось назначить админа.")
            else:
                await message.answer(f"✅ Ресторан \"{restaurant_name}\" успешно создан и админ назначен!")
            
            # Очищаем состояние
            ADD_FLOW.pop(uid, None)
            
    except Exception as e:
        print(f"DEBUG: Error creating restaurant: {e}")
        await message.answer("❌ Ошибка при создании ресторана. Попробуйте снова.")
        ADD_FLOW.pop(uid, None)


@dp.message(F.text == "Удалить ресторан")
async def ga_delete_restaurant(message: types.Message) -> None:
    uid = message.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await message.answer("Нет доступа к удалению ресторана.")
        return
    try:
        async with httpx.AsyncClient(timeout=7) as client:
            r = await client.get(PUBLIC_WEBAPP_URL + "/api/admin/restaurants", headers={"X-Telegram-User-Id": str(uid)})
            data = r.json() if r.status_code == 200 else []
            if not data:
                await message.answer("Список ресторанов пуст.")
                return
            lines = [f"{it['id']}: {it['name']}" for it in data]
            await message.answer("Выберите ресторан для удаления (введите ID):\n" + "\n".join(lines))
            PENDING_INPUT[uid] = {"kind": "ga_delete_select", "list": data}
    except Exception:
        await message.answer("Не удалось получить список ресторанов.")

@dp.callback_query(F.data == "open_menu")
async def open_main_menu(cb: types.CallbackQuery) -> None:
    url = PUBLIC_WEBAPP_URL + f"/static/index.html?uid={cb.from_user.id}&ngrok-skip-browser-warning=1"
    if PUBLIC_WEBAPP_URL.lower().startswith("https://"):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=url))]])
        await cb.message.answer("Mini app", reply_markup=kb)
    else:
        await cb.message.answer("Для открытия mini app нужен HTTPS. Временно откройте по ссылке: " + url)
    await cb.answer()


# -------- Профиль админа: подменю и ввод --------


RESTAURANT_DATA_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Режим работы"), KeyboardButton(text="Адрес")],
        [KeyboardButton(text="Номер телефона")],
        [KeyboardButton(text="Назад")],
    ],
    resize_keyboard=True,
)

ORDER_TERMS_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Минимальная сумма заказа"), KeyboardButton(text="Время доставки")],
        [KeyboardButton(text="Назад")],
    ],
    resize_keyboard=True,
)




@dp.message(F.text == "Данные ресторана")
async def admin_restaurant_data(message: types.Message) -> None:
    if not await _is_restaurant_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    await message.answer("Выберите поле для изменения", reply_markup=RESTAURANT_DATA_KB)


@dp.message(F.text.in_({"Выключить ресторан", "Включить ресторан"}))
async def toggle_restaurant(message: types.Message) -> None:
    uid = message.from_user.id
    if not await _is_restaurant_admin(uid):
        await message.answer("Нет доступа.")
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            info = await client.get(PUBLIC_WEBAPP_URL + "/api/ra/restaurant", headers={"X-Telegram-User-Id": str(uid)})
            r = info.json()
            enabled = not bool(r.get("is_enabled"))
            await client.post(PUBLIC_WEBAPP_URL + f"/api/ra/restaurant/status?enabled={'true' if enabled else 'false'}", headers={"X-Telegram-User-Id": str(uid)})
        await message.answer("Статус обновлён.", reply_markup=RA_INLINE_KB)
    except Exception:
        await message.answer("Не удалось обновить статус.")


@dp.message(F.text == "Заказы")
async def admin_orders(message: types.Message) -> None:
    uid = message.from_user.id
    if not await _is_restaurant_admin(uid):
        await message.answer("Нет доступа.")
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(PUBLIC_WEBAPP_URL + "/api/ra/orders", headers={"X-Telegram-User-Id": str(uid)})
            if res.status_code != 200:
                await message.answer("Нет доступа к заказам.")
                return
            orders = res.json() or []
            if not orders:
                await message.answer("Заказов нет.")
                return
            # Краткая история заказов
            lines = []
            for o in orders[-10:]:
                items = ", ".join([f"{it.get('name','')}×{it.get('qty',0)}" for it in o.get('items', [])])
                lines.append(f"#{o.get('id')} · {o.get('status')} · {o.get('total_price')} р\n{items}")
            await message.answer("История заказов (последние):\n" + "\n\n".join(lines))
    except Exception:
        await message.answer("Ошибка получения заказов.")


# --- Ввод текстовых значений ---

PENDING_INPUT: dict[int, dict] = {}


def _expect(user_id: int, kind: str) -> None:
    PENDING_INPUT[user_id] = {"kind": kind}


@dp.message(F.text == "Режим работы")
async def ask_working_hours(message: types.Message) -> None:
    if not await _is_restaurant_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    _expect(message.from_user.id, "work_hours")
    await message.answer("Напишите режим работы строго в формате: с 10:00 - 20:00")


@dp.message(F.text == "Адрес")
async def ask_address(message: types.Message) -> None:
    if not await _is_restaurant_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    _expect(message.from_user.id, "address")
    await message.answer("Напишите адрес:")


@dp.message(F.text == "Номер телефона")
async def ask_phone(message: types.Message) -> None:
    if not await _is_restaurant_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    _expect(message.from_user.id, "phone")
    await message.answer("Напишите номер телефона:")


@dp.message(F.text == "Условия заказа")
async def open_terms(message: types.Message) -> None:
    if not await _is_restaurant_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    await message.answer("Выберите параметр", reply_markup=ORDER_TERMS_KB)


@dp.message(F.text == "Минимальная сумма заказа")
async def ask_min_sum(message: types.Message) -> None:
    if not await _is_restaurant_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    _expect(message.from_user.id, "min_sum")
    await message.answer("Задайте сумму строго в формате 1500")


@dp.message(F.text == "Время доставки")
async def ask_delivery_time(message: types.Message) -> None:
    if not await _is_restaurant_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    _expect(message.from_user.id, "delivery_time")
    await message.answer("Напишите время доставки строго в минутах, например 90")


@dp.message(F.text == "Назад")
async def go_back(message: types.Message) -> None:
    # Возврат к меню RA
    if await _is_restaurant_admin(message.from_user.id):
        await message.answer("Меню профиля ресторана", reply_markup=RA_INLINE_KB)
    else:
        await message.answer("Главное меню")


# ===========================================
# ОБРАБОТЧИКИ РАССЫЛКИ (ДОЛЖНЫ БЫТЬ ПЕРЕД ОБЩИМ ОБРАБОТЧИКОМ)
# ===========================================

@dp.message(lambda message: message.from_user.id in BROADCAST_FLOW)
async def broadcast_text_handler(message: types.Message) -> None:
    uid = message.from_user.id
    state = BROADCAST_FLOW.get(uid)
    if not state:
        return
    
    # Проверяем, что мы в правильном шаге
    if state.get("step") != "text":
        return
    
    # Обрабатываем медиа
    if message.photo:
        state["media_type"] = "photo"
        state["media_file_id"] = message.photo[-1].file_id
        state["text"] = message.caption or ""
    elif message.video:
        state["media_type"] = "video"
        state["media_file_id"] = message.video.file_id
        state["text"] = message.caption or ""
    elif message.text:
        state["text"] = message.text
        state["media_type"] = None
        state["media_file_id"] = None
    else:
        await message.answer("❌ Поддерживаются только текст, фото и видео.")
        return
    
    # Показываем превью и кнопку подтверждения
    target_names = {
        "all": "всем пользователям",
        "clients": "только клиентам", 
        "restaurants": "только ресторанам"
    }
    
    preview_text = f"📢 <b>Превью рассылки</b>\n\n"
    preview_text += f"<b>Получатели:</b> {target_names[state['target_type']]}\n"
    preview_text += f"<b>Текст:</b> {state['text'][:200]}{'...' if len(state['text']) > 200 else ''}\n"
    
    if state['media_type']:
        preview_text += f"<b>Медиа:</b> {state['media_type']}\n"
    
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")
            ]
        ]
    )
    
    await message.answer(preview_text, reply_markup=confirm_kb, parse_mode="HTML")


@dp.callback_query(F.data == "broadcast_confirm")
async def broadcast_confirm_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    state = BROADCAST_FLOW.get(uid)
    if not state:
        await callback.answer("Состояние рассылки не найдено.")
        return
    
    try:
        # Отправляем рассылку через API
        async with httpx.AsyncClient(timeout=30) as client:
            payload = {
                "text": state["text"],
                "media_type": state["media_type"],
                "media_file_id": state["media_file_id"],
                "target_type": state["target_type"]
            }
            
            response = await client.post(
                INTERNAL_API_URL + "/api/admin/broadcast",
                json=payload,
                headers={"X-Telegram-User-Id": str(uid)}
            )
            
            if response.status_code == 200:
                result = response.json()
                await callback.message.answer(
                    f"✅ <b>Рассылка отправлена!</b>\n\n"
                    f"📊 Отправлено: {result.get('sent', 0)}\n"
                    f"❌ Ошибок: {result.get('failed', 0)}\n"
                    f"📈 Всего получателей: {result.get('total', 0)}",
                    reply_markup=ADMIN_INLINE_KB,
                    parse_mode="HTML"
                )
            else:
                await callback.message.answer(
                    f"❌ Ошибка отправки рассылки: {response.text}",
                    reply_markup=ADMIN_INLINE_KB
                )
    
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=ADMIN_INLINE_KB
        )
    
    finally:
        BROADCAST_FLOW.pop(uid, None)
    
    await callback.answer()


@dp.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel_callback(callback: types.CallbackQuery) -> None:
    uid = callback.from_user.id
    BROADCAST_FLOW.pop(uid, None)
    await callback.message.answer("❌ Рассылка отменена.", reply_markup=ADMIN_INLINE_KB)
    await callback.answer()

# ===========================================
# ОБЩИЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ===========================================

@dp.message()
async def handle_text_inputs(message: types.Message) -> None:
    # Обработка ожидаемого текстового ввода
    uid = message.from_user.id
    
    # Не обрабатываем, если пользователь в состоянии рассылки
    if uid in BROADCAST_FLOW:
        return
    
    task = PENDING_INPUT.get(uid)
    if not task or not message.text:
        return
    kind = task.get("kind")
    text = message.text.strip()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            if kind == "address":
                await client.patch(PUBLIC_WEBAPP_URL + "/api/ra/restaurant", headers={"X-Telegram-User-Id": str(uid)}, json={"address": text})
                await message.answer("Адрес обновлён.", reply_markup=RESTAURANT_DATA_KB)
            elif kind == "phone":
                await client.patch(PUBLIC_WEBAPP_URL + "/api/ra/restaurant", headers={"X-Telegram-User-Id": str(uid)}, json={"phone": text})
                await message.answer("Телефон обновлён.", reply_markup=RESTAURANT_DATA_KB)
            elif kind == "min_sum":
                val = int(text)
                await client.patch(PUBLIC_WEBAPP_URL + "/api/ra/restaurant", headers={"X-Telegram-User-Id": str(uid)}, json={"delivery_min_sum": val})
                await message.answer("Минимальная сумма обновлена.", reply_markup=ORDER_TERMS_KB)
            elif kind == "delivery_time":
                val = int(text)
                await client.patch(PUBLIC_WEBAPP_URL + "/api/ra/restaurant", headers={"X-Telegram-User-Id": str(uid)}, json={"delivery_time_minutes": val})
                await message.answer("Время доставки обновлено.", reply_markup=ORDER_TERMS_KB)
            elif kind == "work_hours":
                # ожидаемый формат: "с HH:MM - HH:MM"
                import re
                m = re.search(r"(\d{1,2}):(\d{2}).*?(\d{1,2}):(\d{2})", text)
                if not m:
                    await message.answer("Неверный формат. Пример: с 10:00 - 20:00")
                else:
                    h1, m1, h2, m2 = map(int, m.groups())
                    open_min = h1 * 60 + m1
                    close_min = h2 * 60 + m2
                    await client.patch(PUBLIC_WEBAPP_URL + "/api/ra/restaurant", headers={"X-Telegram-User-Id": str(uid)}, json={"work_open_min": open_min, "work_close_min": close_min})
                    await message.answer("Режим работы обновлён.", reply_markup=RESTAURANT_DATA_KB)
            elif kind == "ga_add_username":
                state = ADD_FLOW.get(uid)
                if not state:
                    return
                state["username"] = text
                await message.answer("Username сохранён. Теперь введите название (кнопка: Название ресторана).", reply_markup=ADD_REST_KB)
                await _try_finish_add_restaurant(uid, message)
            elif kind == "ga_add_name":
                state = ADD_FLOW.get(uid)
                if not state:
                    return
                state["name"] = text
                await message.answer("Название сохранено. Теперь введите @username (кнопка: @Имя аккаунта).", reply_markup=ADD_REST_KB)
                await _try_finish_add_restaurant(uid, message)
            elif kind == "ga_delete_select":
                # ожидаем ID и подтверждение
                try:
                    rid = int(text)
                except ValueError:
                    await message.answer("Нужно указать ID ресторана.")
                    return
                PENDING_INPUT[uid] = {"kind": "ga_delete_confirm", "rid": rid}
                await message.answer("Точно хотите удалить ресторан?", reply_markup=CONFIRM_KB)
            elif kind == "ga_delete_confirm":
                if text.lower() == "да":
                    rid = PENDING_INPUT.get(uid, {}).get("rid")
                    if not rid:
                        await message.answer("Не найден ID ресторана.")
                        return
                    async with httpx.AsyncClient(timeout=7) as client:
                        await client.delete(PUBLIC_WEBAPP_URL + f"/api/admin/restaurants/{rid}", headers={"X-Telegram-User-Id": str(uid)})
                    await message.answer("Ресторан удалён.", reply_markup=ADMIN_INLINE_KB)
                else:
                    await message.answer("Удаление отменено.", reply_markup=ADMIN_INLINE_KB)
    except ValueError:
        await message.answer("Нужно число. Повторите ввод.")
        return
    except Exception:
        await message.answer("Ошибка сохранения. Попробуйте ещё раз.")
        return
    finally:
        PENDING_INPUT.pop(uid, None)


# --- Обработчики статистики ---

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: types.CallbackQuery) -> None:
    """Обработчик кнопки Статистика"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к статистике.")
        return
    await callback.message.edit_text("📊 Выберите тип статистики:", reply_markup=STATS_KB)
    await callback.answer()


@dp.callback_query(F.data == "stats_global")
async def stats_global_callback(callback: types.CallbackQuery) -> None:
    """Общая статистика по всем ресторанам"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к статистике.")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(INTERNAL_API_URL + "/api/admin/stats", headers={"X-Telegram-User-Id": str(uid)})
            if response.status_code == 200:
                data = response.json()
                
                stats_text = "📊 **Общая статистика по всем ресторанам**\n\n"
                
                # Статистика за месяц
                month_stats = data.get("month", {})
                stats_text += f"📅 **За текущий месяц:**\n"
                stats_text += f"• Заказов: {month_stats.get('orders', 0)} на сумму {month_stats.get('sum', 0):,} ₽\n"
                stats_text += f"• Отмен: {month_stats.get('cancelled', 0)}\n"
                stats_text += f"• Изменений: {month_stats.get('modified', 0)}\n\n"
                
                # Статистика за сегодня
                today_stats = data.get("today", {})
                stats_text += f"📆 **За сегодня:**\n"
                stats_text += f"• Заказов: {today_stats.get('orders', 0)} на сумму {today_stats.get('sum', 0):,} ₽\n"
                stats_text += f"• Отмен: {today_stats.get('cancelled', 0)}\n"
                stats_text += f"• Изменений: {today_stats.get('modified', 0)}\n"
                
                await callback.message.edit_text(stats_text, parse_mode="Markdown", reply_markup=STATS_KB)
            else:
                await callback.message.edit_text("❌ Ошибка получения статистики", reply_markup=STATS_KB)
    except Exception as e:
        logger.exception("Error getting global stats")
        await callback.message.edit_text("❌ Ошибка получения статистики", reply_markup=STATS_KB)
    
    await callback.answer()


@dp.callback_query(F.data == "stats_users")
async def stats_users_callback(callback: types.CallbackQuery) -> None:
    """Статистика пользователей"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к статистике.")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(INTERNAL_API_URL + "/api/admin/stats/users", headers={"X-Telegram-User-Id": str(uid)})
            if response.status_code == 200:
                data = response.json()
                
                stats_text = "👥 **Статистика пользователей**\n\n"
                stats_text += f"📊 **Общие данные:**\n"
                stats_text += f"• Всего пользователей: {data.get('total_users', 0):,}\n"
                stats_text += f"• Заблокированных: {data.get('blocked_users', 0):,}\n\n"
                
                stats_text += f"📅 **За текущий месяц:**\n"
                stats_text += f"• Новых пользователей: {data.get('unique_users_month', 0):,}\n"
                stats_text += f"• Посещений: {data.get('visits_month', 0):,}\n\n"
                
                stats_text += f"📆 **За сегодня:**\n"
                stats_text += f"• Новых пользователей: {data.get('unique_users_today', 0):,}\n"
                stats_text += f"• Посещений: {data.get('visits_today', 0):,}\n"
                
                await callback.message.edit_text(stats_text, parse_mode="Markdown", reply_markup=STATS_KB)
            else:
                await callback.message.edit_text("❌ Ошибка получения статистики пользователей", reply_markup=STATS_KB)
    except Exception as e:
        logger.exception("Error getting user stats")
        await callback.message.edit_text("❌ Ошибка получения статистики пользователей", reply_markup=STATS_KB)
    
    await callback.answer()


@dp.callback_query(F.data == "stats_restaurant")
async def stats_restaurant_callback(callback: types.CallbackQuery) -> None:
    """Выбор ресторана для статистики"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к статистике.")
        return
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(INTERNAL_API_URL + "/api/admin/stats/restaurants", headers={"X-Telegram-User-Id": str(uid)})
            if response.status_code == 200:
                data = response.json()
                restaurants = data.get("restaurants", [])
                
                if not restaurants:
                    await callback.message.edit_text("❌ Нет доступных ресторанов", reply_markup=STATS_KB)
                    return
                
                # Создаем клавиатуру со списком ресторанов
                keyboard = []
                for restaurant in restaurants:
                    status = "✅" if restaurant.get("is_enabled") else "❌"
                    keyboard.append([
                        InlineKeyboardButton(
                            text=f"{status} {restaurant['name']}", 
                            callback_data=f"stats_rest_{restaurant['id']}"
                        )
                    ])
                
                keyboard.append([InlineKeyboardButton(text="← Назад", callback_data="admin_stats")])
                
                kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
                await callback.message.edit_text("🏪 Выберите ресторан для статистики:", reply_markup=kb)
            else:
                await callback.message.edit_text("❌ Ошибка получения списка ресторанов", reply_markup=STATS_KB)
    except Exception as e:
        logger.exception("Error getting restaurants list")
        await callback.message.edit_text("❌ Ошибка получения списка ресторанов", reply_markup=STATS_KB)
    
    await callback.answer()


@dp.callback_query(F.data.startswith("stats_rest_"))
async def stats_restaurant_detail_callback(callback: types.CallbackQuery) -> None:
    """Статистика конкретного ресторана"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к статистике.")
        return
    
    restaurant_id = int(callback.data.split("_")[-1])
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Получаем статистику ресторана
            stats_response = await client.get(
                INTERNAL_API_URL + f"/api/admin/stats/by-restaurant?restaurant_id={restaurant_id}", 
                headers={"X-Telegram-User-Id": str(uid)}
            )
            
            # Получаем название ресторана
            restaurants_response = await client.get(
                INTERNAL_API_URL + "/api/admin/stats/restaurants", 
                headers={"X-Telegram-User-Id": str(uid)}
            )
            
            if stats_response.status_code == 200 and restaurants_response.status_code == 200:
                stats_data = stats_response.json()
                restaurants_data = restaurants_response.json()
                
                # Находим название ресторана
                restaurant_name = "Неизвестный ресторан"
                for restaurant in restaurants_data.get("restaurants", []):
                    if restaurant["id"] == restaurant_id:
                        restaurant_name = restaurant["name"]
                        break
                
                stats_text = f"🏪 **Статистика ресторана \"{restaurant_name}\"**\n\n"
                
                # Статистика за месяц
                month_stats = stats_data.get("month", {})
                stats_text += f"📅 **За текущий месяц:**\n"
                stats_text += f"• Заказов: {month_stats.get('orders', 0)} на сумму {month_stats.get('sum', 0):,} ₽\n"
                stats_text += f"• Отмен: {month_stats.get('cancelled', 0)}\n"
                stats_text += f"• Изменений: {month_stats.get('modified', 0)}\n\n"
                
                # Статистика за сегодня
                today_stats = stats_data.get("today", {})
                stats_text += f"📆 **За сегодня:**\n"
                stats_text += f"• Заказов: {today_stats.get('orders', 0)} на сумму {today_stats.get('sum', 0):,} ₽\n"
                stats_text += f"• Отмен: {today_stats.get('cancelled', 0)}\n"
                stats_text += f"• Изменений: {today_stats.get('modified', 0)}\n"
                
                # Кнопка назад к выбору ресторана
                back_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← К списку ресторанов", callback_data="stats_restaurant")],
                    [InlineKeyboardButton(text="← К статистике", callback_data="admin_stats")]
                ])
                
                await callback.message.edit_text(stats_text, parse_mode="Markdown", reply_markup=back_kb)
            else:
                await callback.message.edit_text("❌ Ошибка получения статистики ресторана", reply_markup=STATS_KB)
    except Exception as e:
        logger.exception("Error getting restaurant stats")
        await callback.message.edit_text("❌ Ошибка получения статистики ресторана", reply_markup=STATS_KB)
    
    await callback.answer()


# Обработчики для конкретных действий с ресторанами
@dp.callback_query(F.data.startswith("enable_rest_"))
async def enable_restaurant_callback(callback: types.CallbackQuery) -> None:
    """Включение ресторана"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к операции включения ресторана.")
        return
    
    restaurant_id = int(callback.data.split("_")[-1])
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.patch(
                INTERNAL_API_URL + f"/api/admin/restaurants/{restaurant_id}",
                headers={"X-Telegram-User-Id": str(uid), "Content-Type": "application/json"},
                json={"is_enabled": True}
            )
            
            if response.status_code == 200:
                await callback.message.edit_text("✅ Ресторан успешно включен!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
                ]))
            else:
                await callback.message.edit_text("❌ Ошибка при включении ресторана", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
                ]))
    except Exception as e:
        logger.exception("Error enabling restaurant")
        await callback.message.edit_text("❌ Ошибка при включении ресторана", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
        ]))
    
    await callback.answer()


@dp.callback_query(F.data.startswith("disable_rest_"))
async def disable_restaurant_callback(callback: types.CallbackQuery) -> None:
    """Выключение ресторана"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к операции выключения ресторана.")
        return
    
    restaurant_id = int(callback.data.split("_")[-1])
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.patch(
                INTERNAL_API_URL + f"/api/admin/restaurants/{restaurant_id}",
                headers={"X-Telegram-User-Id": str(uid), "Content-Type": "application/json"},
                json={"is_enabled": False}
            )
            
            if response.status_code == 200:
                await callback.message.edit_text("❌ Ресторан успешно выключен!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
                ]))
            else:
                await callback.message.edit_text("❌ Ошибка при выключении ресторана", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
                ]))
    except Exception as e:
        logger.exception("Error disabling restaurant")
        await callback.message.edit_text("❌ Ошибка при выключении ресторана", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
        ]))
    
    await callback.answer()


@dp.callback_query(F.data.startswith("delete_rest_"))
async def delete_restaurant_confirm_callback(callback: types.CallbackQuery) -> None:
    """Подтверждение удаления ресторана"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к операции удаления ресторана.")
        return
    
    restaurant_id = int(callback.data.split("_")[-1])
    
    # Получаем название ресторана для отображения
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(INTERNAL_API_URL + "/api/admin/restaurants", headers={"X-Telegram-User-Id": str(uid)})
            if response.status_code == 200:
                restaurants = response.json()
                restaurant_name = "Неизвестный ресторан"
                for restaurant in restaurants:
                    if restaurant["id"] == restaurant_id:
                        restaurant_name = restaurant["name"]
                        break
                
                # Создаем клавиатуру подтверждения
                confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{restaurant_id}")],
                    [InlineKeyboardButton(text="❌ Нет, отменить", callback_data="admin_delete_restaurant")],
                    [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
                ])
                
                await callback.message.edit_text(
                    f"🗑️ **Точно хотите удалить ресторан \"{restaurant_name}\"?**\n\n"
                    "⚠️ Это действие нельзя отменить!",
                    parse_mode="Markdown",
                    reply_markup=confirm_kb
                )
            else:
                await callback.message.edit_text("❌ Ошибка получения данных ресторана")
    except Exception as e:
        logger.exception("Error getting restaurant data for delete confirmation")
        await callback.message.edit_text("❌ Ошибка получения данных ресторана")
    
    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_restaurant_callback(callback: types.CallbackQuery) -> None:
    """Подтвержденное удаление ресторана"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к операции удаления ресторана.")
        return
    
    restaurant_id = int(callback.data.split("_")[-1])
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.delete(
                INTERNAL_API_URL + f"/api/admin/restaurants/{restaurant_id}",
                headers={"X-Telegram-User-Id": str(uid)}
            )
            
            if response.status_code == 200:
                await callback.message.edit_text("🗑️ Ресторан успешно удален!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
                ]))
            else:
                await callback.message.edit_text("❌ Ошибка при удалении ресторана", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
                ]))
    except Exception as e:
        logger.exception("Error deleting restaurant")
        await callback.message.edit_text("❌ Ошибка при удалении ресторана", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="admin_back")]
        ]))
    
    await callback.answer()


@dp.callback_query(F.data == "admin_back")
async def admin_back_callback(callback: types.CallbackQuery) -> None:
    """Возврат в главное меню админки"""
    uid = callback.from_user.id
    if uid not in SUPER_ADMIN_IDS:
        await callback.answer("Нет доступа к админке.")
        return
    
    await callback.message.edit_text("🔧 Главное меню админки:", reply_markup=ADMIN_INLINE_KB)
    await callback.answer()


@dp.message(Command("ra"))
async def restaurant_admin_entry(message: types.Message) -> None:
    if not PUBLIC_WEBAPP_URL.lower().startswith("https://"):
        await message.answer("Для админки нужен HTTPS URL.")
        return
    url = PUBLIC_WEBAPP_URL + f"/static/ra.html?uid={message.from_user.id}&ngrok-skip-browser-warning=1&v=1"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Админка ресторана", web_app=WebAppInfo(url=url))]]
    )
    await message.answer("Админка ресторана", reply_markup=kb)


# === ОБРАБОТЧИКИ ДЛЯ РАССЫЛКИ ===

@dp.message(lambda message: message.text and message.text.lower() == "отмена" and message.from_user.id in BROADCAST_FLOW)
async def broadcast_cancel(message: types.Message) -> None:
    uid = message.from_user.id
    if uid in BROADCAST_FLOW:
        BROADCAST_FLOW.pop(uid, None)
    await message.answer("❌ Рассылка отменена.", reply_markup=ADMIN_INLINE_KB)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is required")
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

