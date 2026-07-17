<img width="1815" height="662" alt="{6F16E4FC-01D5-41EB-A347-81C2872D8CAE}" src="https://github.com/user-attachments/assets/c4f29500-3424-4742-a0e7-f08a4c2336b3" />

# Comal Auto Aspect Ratio

Qwen-Image-Edit(2509/2511), Flux.2 Klein 등 이미지 편집 모델에서 발생하는
**픽셀 시프트/줌 현상**을 방지하기 위한 ComfyUI 커스텀 노드입니다.

원본 이미지를 Qwen-Image가 학습한 공식 종횡비(1:1, 16:9, 9:16, 4:3, 3:4,
3:2, 2:3, 21:9, 9:21) 중 하나에 맞춰 자동(또는 수동)으로 패딩하고,
편집이 끝난 뒤 원본 크기/위치로 정확히 복원합니다.

## 배경

Qwen Image Edit류 모델은 내부 텍스트 인코더 노드가 입력 이미지를
강제로 재리스케일하는데, 이때 레퍼런스 latent와 출력 latent의 크기가
미세하게 어긋나면서 결과물이 원본 대비 확대/축소/이동되는 현상이
발생합니다. 이 노드는 입력을 미리 안전한 해상도로 패딩해서 이 문제를
줄여줍니다.

## 설치

이 저장소를 `ComfyUI/custom_nodes/` 폴더 안에 클론하세요.

\`\`\`bash
cd ComfyUI/custom_nodes
git clone https://github.com/comal0731/auto_aspect_ratio.git comal-auto
\`\`\`

ComfyUI를 재시작하면 노드 검색창에서 "Comal"로 검색하면 나타납니다.

## 노드 구성

### Comal - Auto Aspect Pad (Qwen)

| 입력 | 설명 |
| --- | --- |
| image | 원본 이미지 |
| aspect_ratio | `auto`(원본과 가장 가까운 비율 자동 선택) 또는 직접 지정 |
| megapixels | 목표 총 픽셀수(기본 1.0 ≈ 1024×1024) |
| multiple | 정렬 배수(기본 8, Qwen Edit VAE 요구사항) |

| 출력 | 설명 |
| --- | --- |
| image | 패딩된 이미지 |
| width / height | 패딩된 캔버스의 실제 크기 (EmptyLatentImage에 연결) |
| pad_info | 복원에 필요한 정보 묶음 (Unpad 노드로 그대로 연결) |

### Comal - Auto Aspect Unpad (Restore)

| 입력 | 설명 |
| --- | --- |
| image | 편집이 끝난 결과 이미지 |
| pad_info | Pad 노드에서 나온 값 그대로 연결 |

출력으로 원본과 동일한 크기의 이미지가 나옵니다.

## 사용 예시 (Qwen Image Edit)

1. Load Image → Comal Auto Aspect Pad
2. Pad의 `width`, `height` → EmptyLatentImage
3. Pad의 `image` → (VAE Encode → ReferenceLatent, 텍스트 인코더의 VAE
   입력은 연결하지 않는 것을 권장)
4. KSampler → VAE Decode → Comal Auto Aspect Unpad (pad_info 연결)

## 라이선스

MIT
