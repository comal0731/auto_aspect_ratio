import torch
import torch.nn.functional as F
import math

QWEN_RATIOS = {
    "1:1": (1, 1),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "21:9": (21, 9),
    "9:21": (9, 21),
}

ASPECT_RATIO_OPTIONS = ["auto"] + list(QWEN_RATIOS.keys())


class AutoAspectPad:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "aspect_ratio": (ASPECT_RATIO_OPTIONS, {"default": "auto"}),
                "megapixels": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.05}),
                "multiple": ("INT", {"default": 8, "min": 8, "max": 128, "step": 8}),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT", "PADINFO")
    RETURN_NAMES = ("image", "width", "height", "pad_info")
    FUNCTION = "run"
    CATEGORY = "image/resize"

    def run(self, image, aspect_ratio, megapixels, multiple):
        b, h, w, c = image.shape
        orig_ratio = w / h

        if aspect_ratio == "auto":
            # 원본과 가장 가까운 공식 비율을 자동으로 판단
            best_rw, best_rh, best_diff = 1, 1, float("inf")
            for rw, rh in QWEN_RATIOS.values():
                diff = abs(math.log(rw / rh) - math.log(orig_ratio))
                if diff < best_diff:
                    best_diff, best_rw, best_rh = diff, rw, rh
        else:
            # 사용자가 직접 고른 비율 사용
            best_rw, best_rh = QWEN_RATIOS[aspect_ratio]

        target_pixels = megapixels * 1024 * 1024
        s = math.sqrt(target_pixels / (best_rw * best_rh))
        target_w = max(multiple, round(best_rw * s / multiple) * multiple)
        target_h = max(multiple, round(best_rh * s / multiple) * multiple)

        scale = min(target_w / w, target_h / h)
        inner_w = max(1, round(w * scale))
        inner_h = max(1, round(h * scale))

        img = image.movedim(-1, 1)
        resized = F.interpolate(img, size=(inner_h, inner_w), mode="bilinear", align_corners=False)

        pad_left = (target_w - inner_w) // 2
        pad_top = (target_h - inner_h) // 2

        canvas = torch.zeros((b, c, target_h, target_w), dtype=img.dtype)
        canvas[:, :, pad_top:pad_top + inner_h, pad_left:pad_left + inner_w] = resized

        out = canvas.movedim(1, -1)

        pad_info = {
            "orig_w": w, "orig_h": h,
            "pad_left": pad_left, "pad_top": pad_top,
            "inner_w": inner_w, "inner_h": inner_h,
        }
        return (out, target_w, target_h, pad_info)


class AutoAspectUnpad:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "pad_info": ("PADINFO",),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    CATEGORY = "image/resize"

    def run(self, image, pad_info):
        orig_w = pad_info["orig_w"]
        orig_h = pad_info["orig_h"]
        pad_left = pad_info["pad_left"]
        pad_top = pad_info["pad_top"]
        inner_w = pad_info["inner_w"]
        inner_h = pad_info["inner_h"]

        img = image.movedim(-1, 1)
        cropped = img[:, :, pad_top:pad_top + inner_h, pad_left:pad_left + inner_w]
        restored = F.interpolate(cropped, size=(orig_h, orig_w), mode="bilinear", align_corners=False)
        return (restored.movedim(1, -1),)


NODE_CLASS_MAPPINGS = {
    "AutoAspectPad": AutoAspectPad,
    "AutoAspectUnpad": AutoAspectUnpad,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AutoAspectPad": "Comal - Auto Aspect Pad (Qwen)",
    "AutoAspectUnpad": "Comal - Auto Aspect Unpad (Restore)",
}
