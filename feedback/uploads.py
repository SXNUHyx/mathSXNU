from pathlib import Path
import warnings
import zipfile
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError
import olefile


def inspect_upload(upload):
    suffix = Path(upload.name).suffix.lower()
    if any(ord(c) < 32 for c in upload.name):
        raise ValidationError("文件名不能包含控制字符。")
    image_types = {".jpg": ("JPEG", "image/jpeg"), ".jpeg": ("JPEG", "image/jpeg"), ".png": ("PNG", "image/png"), ".webp": ("WEBP", "image/webp")}
    if upload.size == 0:
        raise ValidationError("不能上传空文件。")
    if suffix not in {*image_types, ".pdf", ".ppt", ".pptx"}:
        raise ValidationError("支持JPG、PNG、WEBP图片以及PDF、PPT、PPTX资料。")
    if upload.size > (5 if suffix in image_types else 25) * 1024 * 1024:
        raise ValidationError("图片最大5MB，课程资料最大25MB。")
    try:
        upload.seek(0)
        if suffix in image_types:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(upload) as image:
                    if image.format != image_types[suffix][0] or image.width * image.height > 25_000_000:
                        raise ValidationError("图片格式不匹配，或图片尺寸超过2500万像素。")
                    image.verify()
            return image_types[suffix][1], True
        if suffix == ".pdf":
            if not upload.read(8).startswith(b"%PDF-"):
                raise ValidationError("文件内容不是有效的PDF格式。")
            return "application/pdf", False
        if suffix == ".pptx":
            with zipfile.ZipFile(upload) as archive:
                items = archive.infolist()
                names = {i.filename for i in items}
                if len(items) > 3000 or sum(i.file_size for i in items) > 250 * 1024 * 1024:
                    raise ValidationError("PPTX内容过大，请压缩或拆分后上传。")
                if not {"[Content_Types].xml", "ppt/presentation.xml"}.issubset(names) or any("vbaproject" in n.lower() for n in names):
                    raise ValidationError("不是支持的无宏PPTX演示文件。")
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation", False
        with olefile.OleFileIO(upload) as document:
            if not document.exists("PowerPoint Document"):
                raise ValidationError("文件内容不是PPT演示文稿。")
        return "application/vnd.ms-powerpoint", False
    except (UnidentifiedImageError, OSError, ValueError, zipfile.BadZipFile, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError("文件损坏或格式不匹配，请检查后重新上传。") from exc
    finally:
        upload.seek(0)
