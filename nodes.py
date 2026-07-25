import torch
import torch.nn.functional as F
import math
import numpy as np
from PIL import Image

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
INTERPOLATION_OPTIONS = ["lanczos", "bicubic", "bilinear"]

# 원본과 이 값보다 더 가까운 비율은 "거의 정확히 일치"로 간주하고 건너뜀 (단, 1:1은 예외)
EXACT_MATCH_EPS = 0.02


def resize_tensor(img, size, mode="lanczos"):
    target_h, target_w = size

    if mode != "lanczos":
        return F.interpolate(img, size=(target_h, target_w), mode=mode, align_corners=False)

    b, c, h, w = img.shape
    device, dtype = img.device, img.dtype
    img_cpu = img.detach().cpu()
    out = torch.empty((b, c, target_h, target_w), dtype=dtype)

    pil_mode = {1: "L", 3: "RGB", 4: "RGBA"}.get(c, "RGB")
    for i in range(b):
        arr = img_cpu[i].movedim(0, -1).clamp(0, 1).numpy()
        arr = (arr * 255.0 + 0.5).astype(np.uint8)
        pil_img = Image.fromarray(arr if c > 1 else arr[:, :, 0], mode=pil_mode)
        pil_resized = pil_img.resize((target_w, target_h), resample=Image.LANCZOS)
        arr_resized = np.array(pil_resized).astype(np.float32) / 255.0
        if c == 1:
            arr_resized = arr_resized[:, :, None]
        out[i] = torch.from_numpy(arr_resized).movedim(-1, 0).to(dtype)

    return out.to(device)


class AutoAspectPad:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "aspect_ratio": (ASPECT_RATIO_OPTIONS, {"default": "auto"}),
                "megapixels": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.05}),
                "multiple": ("INT", {"default": 8, "min": 8, "max": 128, "step": 8}),
                "interpolation": (INTERPOLATION_OPTIONS, {"default": "lanczos"}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT", "PADINFO", "MASK")
    RETURN_NAMES = ("image", "width", "height", "pad_info", "mask")
    FUNCTION = "run"
    CATEGORY = "image/resize"

    def run(self, image, aspect_ratio, megapixels, multiple, interpolation, mask=None):
        b, h, w, c = image.shape
        orig_ratio = w / h

        if aspect_ratio == "auto":
            candidates = []
            for key, (rw, rh) in QWEN_RATIOS.items():
                diff = abs(math.log(rw / rh) - math.log(orig_ratio))
                candidates.append((diff, key, rw, rh))
            candidates.sort(key=lambda x: x[0])

            top_diff, top_key, top_rw, top_rh = candidates[0]

            if top_key == "1:1":
                # 1:1은 패딩이 항상 대칭이라 건너뛸 필요 없음
                best_rw, best_rh = top_rw, top_rh
            elif len(candidates) > 1 and top_diff < EXACT_MATCH_EPS:
                _, _, best_rw, best_rh = candidates[1]
            else:
                best_rw, best_rh = top_rw, top_rh
        else:
            best_rw, best_rh = QWEN_RATIOS[aspect_ratio]

        target_pixels = megapixels * 1024 * 1024
        s = math.sqrt(target_pixels / (best_rw * best_rh))
        target_w = max(multiple, round(best_rw * s / multiple) * multiple)
        target_h = max(multiple, round(best_rh * s / multiple) * multiple)

        scale = min(target_w / w, target_h / h)
        inner_w = max(1, round(w * scale))
        inner_h = max(1, round(h * scale))

        img = image.movedim(-1, 1)
        resized = resize_tensor(img, (inner_h, inner_w), mode=interpolation)

        pad_left = (target_w - inner_w) // 2
        pad_top = (target_h - inner_h) // 2

        canvas = torch.zeros(
            (b, c, target_h, target_w),
            dtype=img.dtype,
            device=img.device,
        )
        canvas[:, :, pad_top:pad_top + inner_h, pad_left:pad_left + inner_w] = resized

        out = canvas.movedim(1, -1)

        if mask is None:
            out_mask = torch.zeros(
                (b, target_h, target_w),
                dtype=image.dtype,
                device=image.device,
            )
        else:
            mask = mask.to(device=image.device, dtype=image.dtype)
            if mask.ndim == 2:
                mask = mask.unsqueeze(0)
            if mask.shape[0] == 1 and b > 1:
                mask = mask.expand(b, -1, -1)
            elif mask.shape[0] != b:
                raise ValueError(
                    f"Mask batch size ({mask.shape[0]}) must be 1 or match "
                    f"the image batch size ({b})."
                )

            resized_mask = resize_tensor(
                mask.unsqueeze(1),
                (inner_h, inner_w),
                mode=interpolation,
            ).squeeze(1)
            out_mask = torch.zeros(
                (b, target_h, target_w),
                dtype=resized_mask.dtype,
                device=resized_mask.device,
            )
            out_mask[
                :,
                pad_top:pad_top + inner_h,
                pad_left:pad_left + inner_w,
            ] = resized_mask

        pad_info = {
            "orig_w": w, "orig_h": h,
            "pad_left": pad_left, "pad_top": pad_top,
            "inner_w": inner_w, "inner_h": inner_h,
            "interpolation": interpolation,
        }
        return (out, target_w, target_h, pad_info, out_mask)


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
        mode = pad_info.get("interpolation", "lanczos")

        img = image.movedim(-1, 1)
        cropped = img[:, :, pad_top:pad_top + inner_h, pad_left:pad_left + inner_w]
        restored = resize_tensor(cropped, (orig_h, orig_w), mode=mode)
        return (restored.movedim(1, -1),)


NODE_CLASS_MAPPINGS = {
    "AutoAspectPad": AutoAspectPad,
    "AutoAspectUnpad": AutoAspectUnpad,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AutoAspectPad": "Auto Aspect Pad Comal",
    "AutoAspectUnpad": "Auto Aspect Unpad Comal",
}
