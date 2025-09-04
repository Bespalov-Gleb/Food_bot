import os
import uuid
from PIL import Image
from typing import Tuple, Optional
import io


class ImageProcessor:
    """Сервис для обработки изображений с автоматическим созданием разных размеров"""
    
    # Размеры для разных типов изображений
    SIZES = {
        'dish_card': (200, 200),      # Карточка блюда в меню
        'dish_detail': (400, 400),    # Детальный просмотр блюда
        'restaurant_banner': (800, 400),  # Баннер ресторана
        'restaurant_card': (400, 200),    # Карточка ресторана в списке
        'selection_card': (300, 200),     # Карточка в подборках
    }
    
    @staticmethod
    def process_image(image_data: bytes, original_filename: str, base_dir: str = "uploads") -> dict:
        """
        Обрабатывает загруженное изображение и создает версии разных размеров
        
        Args:
            image_data: Байты изображения
            original_filename: Оригинальное имя файла
            base_dir: Базовая директория для сохранения
            
        Returns:
            dict: Словарь с URL'ами для разных размеров
        """
        try:
            # Открываем изображение
            image = Image.open(io.BytesIO(image_data))
            
            # Конвертируем в RGB если нужно
            if image.mode in ('RGBA', 'LA', 'P'):
                # Создаем белый фон для прозрачных изображений
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Генерируем базовое имя файла
            file_extension = os.path.splitext(original_filename)[1] if original_filename else '.jpg'
            if file_extension.lower() not in ['.jpg', '.jpeg', '.png']:
                file_extension = '.jpg'
            
            base_filename = str(uuid.uuid4())
            
            # Создаем папки если их нет
            for size_name in ImageProcessor.SIZES.keys():
                size_dir = os.path.join(base_dir, size_name)
                if not os.path.exists(size_dir):
                    os.makedirs(size_dir)
            
            # Создаем версии разных размеров
            urls = {}
            for size_name, (width, height) in ImageProcessor.SIZES.items():
                # Создаем копию изображения
                resized_image = image.copy()
                
                # Изменяем размер с сохранением пропорций
                resized_image.thumbnail((width, height), Image.Resampling.LANCZOS)
                
                # Создаем новое изображение нужного размера с белым фоном
                final_image = Image.new('RGB', (width, height), (255, 255, 255))
                
                # Центрируем изображение
                x = (width - resized_image.width) // 2
                y = (height - resized_image.height) // 2
                final_image.paste(resized_image, (x, y))
                
                # Сохраняем
                filename = f"{base_filename}{file_extension}"
                file_path = os.path.join(base_dir, size_name, filename)
                
                # Сохраняем с оптимизацией
                if file_extension.lower() in ['.jpg', '.jpeg']:
                    final_image.save(file_path, 'JPEG', quality=85, optimize=True)
                else:
                    final_image.save(file_path, 'PNG', optimize=True)
                
                urls[size_name] = f"/uploads/{size_name}/{filename}"
            
            # Сохраняем оригинал
            original_filename = f"{base_filename}_original{file_extension}"
            original_path = os.path.join(base_dir, "original", original_filename)
            if not os.path.exists(os.path.join(base_dir, "original")):
                os.makedirs(os.path.join(base_dir, "original"))
            
            if file_extension.lower() in ['.jpg', '.jpeg']:
                image.save(original_path, 'JPEG', quality=90, optimize=True)
            else:
                image.save(original_path, 'PNG', optimize=True)
            
            urls['original'] = f"/uploads/original/{original_filename}"
            
            return {
                "status": "ok",
                "urls": urls,
                "original_size": image.size,
                "processed_sizes": ImageProcessor.SIZES
            }
            
        except Exception as e:
            raise Exception(f"Ошибка при обработке изображения: {str(e)}")
    
    @staticmethod
    def get_url_for_size(base_url: str, size_name: str) -> str:
        """
        Получает URL для конкретного размера изображения
        
        Args:
            base_url: Базовый URL (например, /uploads/dish_card/abc123.jpg)
            size_name: Название размера (dish_card, dish_detail, etc.)
            
        Returns:
            str: URL для нужного размера
        """
        if not base_url:
            return ""
        
        # Извлекаем имя файла из базового URL
        filename = os.path.basename(base_url)
        
        # Формируем новый URL
        return f"/uploads/{size_name}/{filename}"
    
    @staticmethod
    def delete_image_variants(base_filename: str, base_dir: str = "uploads") -> bool:
        """
        Удаляет все варианты изображения
        
        Args:
            base_filename: Базовое имя файла (без расширения)
            base_dir: Базовая директория
            
        Returns:
            bool: True если удаление прошло успешно
        """
        try:
            # Удаляем все размеры
            for size_name in ImageProcessor.SIZES.keys():
                size_dir = os.path.join(base_dir, size_name)
                for ext in ['.jpg', '.jpeg', '.png']:
                    file_path = os.path.join(size_dir, f"{base_filename}{ext}")
                    if os.path.exists(file_path):
                        os.remove(file_path)
            
            # Удаляем оригинал
            original_dir = os.path.join(base_dir, "original")
            for ext in ['.jpg', '.jpeg', '.png']:
                file_path = os.path.join(original_dir, f"{base_filename}_original{ext}")
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            return True
        except Exception:
            return False 