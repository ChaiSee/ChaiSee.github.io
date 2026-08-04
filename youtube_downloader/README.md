# youtube_downloader

YouTube 영상을 **다운로드**하고, 원하는 **시작~끝 구간만 잘라내는(길이 편집)** 파이썬 도구입니다.

- 다운로드: [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
- 구간 자르기: [`ffmpeg`](https://ffmpeg.org/)

원본 아이디어: <https://gist.github.com/shhommychon/759036d8f19f868407190ccf8ca75040>

> ⚠️ 유튜브 이용약관과 저작권을 준수하는 범위(본인 콘텐츠, 공정 이용 등)에서만 사용하세요.

## 구성

| 파일 | 설명 |
| --- | --- |
| `youtube_downloader.py` | 재사용 모듈 + CLI (다운로드 / 구간 자르기) |
| `__main__.py` | `python -m youtube_downloader` 진입점 |
| `my_youtube_download.ipynb` | Colab/Jupyter 노트북 예제 |
| `requirements.txt` | 파이썬 의존성 (`yt-dlp`) |

## 설치

```bash
pip install -r youtube_downloader/requirements.txt
```

추가로 `ffmpeg` 가 필요합니다.

```bash
# macOS
brew install ffmpeg
# Ubuntu/Debian
sudo apt install ffmpeg
```

## CLI 사용법

```bash
# 다운로드만
python -m youtube_downloader "https://youtu.be/VIDEO_ID"

# 다운로드 + 00:30 ~ 01:45 구간 자르기
python -m youtube_downloader "https://youtu.be/VIDEO_ID" --start 00:30 --end 01:45
```

주요 옵션:

| 옵션 | 설명 |
| --- | --- |
| `-s`, `--start` / `-e`, `--end` | 자를 구간 (둘 다 지정해야 자르기 동작) |
| `-o`, `--output-dir` | 저장 폴더 (기본: `downloads`) |
| `--out` | 결과 파일 경로 직접 지정 |
| `--keep-full` | 자른 뒤에도 원본(전체) 파일 유지 |
| `--resolution` | 최대 세로 해상도(px). 예: `1080`, `720` |
| `--cookies` | 연령 제한/로그인 영상용 `cookies.txt` 경로 |
| `--copy` | 재인코딩 없이 빠르게 자르기(키프레임 단위, 시작점이 약간 어긋날 수 있음) |
| `-q`, `--quiet` | 진행 로그 숨김 |

시간 형식은 `초`(`90`), `분:초`(`01:30`), `시:분:초`(`01:02:03`) 를 지원합니다.

## 모듈로 사용

```python
from youtube_downloader import download, trim, download_and_trim

# 1) 다운로드만
path = download("https://youtu.be/VIDEO_ID", output_dir="downloads")

# 2) 이미 받은 영상에서 구간 자르기
clip = trim(path, start="00:30", end="01:45")

# 3) 다운로드 + 자르기 한 번에
result = download_and_trim(
    "https://youtu.be/VIDEO_ID",
    start="00:30",
    end="01:45",
    keep_full=False,
)
```

## Colab

`my_youtube_download.ipynb` 를 [Google Colab](https://colab.research.google.com/) 에서 열고
셀을 위에서부터 실행하면 설치 → 다운로드 → 구간 자르기까지 바로 확인할 수 있습니다.
