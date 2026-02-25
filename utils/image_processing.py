from PIL import Image, ImageEnhance, ImageFilter
import os

def process_image_for_ocr(image_path: str, output_path: str):
    """
    Enhances an image for better OCR/Vision performance:
    - Converts to RGB
    - Increases Contrast
    - Sharpens
    """
    try:
        img = Image.open(image_path)
        img = img.convert('RGB')
        
        # Increase Contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5) # Increase contrast by 50%
        
        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        
        img.save(output_path, quality=95)
        return True
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return False
