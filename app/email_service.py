import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("FROM_EMAIL", "")
        self.webapp_url = os.getenv("WEBAPP_URL", "")
        
    def send_order_notification(self, restaurant_email: str, restaurant_name: str, order_data: Dict[str, Any]) -> bool:
        """
        Отправляет уведомление о новом заказе на email ресторана
        """
        if not restaurant_email or not self.smtp_username or not self.smtp_password:
            logger.warning("Email notification skipped: missing email or SMTP credentials")
            return False
            
        try:
            # Формируем содержимое заказа
            order_items = []
            total = 0
            
            for item in order_data.get('items', []):
                item_total = item['price'] * item['qty']
                total += item_total
                order_items.append(f"• {item['name']} × {item['qty']} - {item_total} ₽")
            
            # Формируем email
            subject = f"Новый заказ #{order_data['id']} - {restaurant_name}"
            
            # Создаем HTML версию письма
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #3b82f6; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                    .content {{ background: #f8fafc; padding: 20px; border-radius: 0 0 8px 8px; }}
                    .order-info {{ background: white; padding: 15px; margin: 15px 0; border-radius: 6px; border-left: 4px solid #3b82f6; }}
                    .order-items {{ background: white; padding: 15px; margin: 15px 0; border-radius: 6px; }}
                    .total {{ font-weight: bold; font-size: 18px; color: #1f2937; }}
                    .button {{ display: inline-block; background: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 15px; }}
                    .button:hover {{ background: #059669; }}
                    .footer {{ text-align: center; margin-top: 20px; color: #6b7280; font-size: 14px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Новый заказ #{order_data['id']}</h1>
                        <p>Ресторан: {restaurant_name}</p>
                    </div>
                    
                    <div class="content">
                        <div class="order-info">
                            <h3>Информация о заказе</h3>
                            <p><strong>Статус:</strong> Обрабатывается оператором</p>
                            <p><strong>Дата:</strong> {order_data.get('created_at', 'Не указана')}</p>
                            <p><strong>Адрес доставки:</strong> {order_data.get('delivery_address', 'Не указан')}</p>
                            <p><strong>Способ оплаты:</strong> {order_data.get('payment_method', 'Не указан')}</p>
                        </div>
                        
                        <div class="order-items">
                            <h3>Состав заказа</h3>
                            {''.join(order_items)}
                            <hr style="margin: 15px 0;">
                            <p class="total">Итого: {total} ₽</p>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="{self.webapp_url}/static/ra.html?order_id={order_data['id']}&uid={order_data.get('user_id', '')}" class="button">
                                Открыть заказ в боте
                            </a>
                        </div>
                        
                        <div class="footer">
                            <p>Это автоматическое уведомление. Не отвечайте на это письмо.</p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Создаем текстовую версию письма
            text_content = f"""
Новый заказ #{order_data['id']} - {restaurant_name}

Статус: Обрабатывается оператором
Дата: {order_data.get('created_at', 'Не указана')}
Адрес доставки: {order_data.get('delivery_address', 'Не указан')}
Способ оплаты: {order_data.get('payment_method', 'Не указан')}

Состав заказа:
{chr(10).join(order_items)}

Итого: {total} ₽

Для обработки заказа перейдите по ссылке:
{self.webapp_url}/static/ra.html?order_id={order_data['id']}&uid={order_data.get('user_id', '')}

Это автоматическое уведомление. Не отвечайте на это письмо.
            """
            
            # Создаем сообщение
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = restaurant_email
            
            # Добавляем части сообщения
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            html_part = MIMEText(html_content, 'html', 'utf-8')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Отправляем email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Order notification email sent to {restaurant_email} for order #{order_data['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send order notification email: {e}")
            return False

# Создаем глобальный экземпляр сервиса
email_service = EmailService() 