# -*- coding: utf-8 -*-
"""YouTube 영상 다운로드 및 구간 자르기(길이 편집) 유틸리티.

- 다운로드: ``yt-dlp`` 사용
- 구간 자르기: ``ffmpeg`` 사용 (시작~끝 구간만 추출)

이 파일은 재사용 가능한 모듈이면서, 그대로 CLI로도 실행할 수 있습니다.

    python -m youtube_downloader "<URL>" --start 00:30 --end 01:45

원본 아이디어: https://gist.github.com/shhommychon/759036d8f19f868407190ccf8ca75040
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

__all__ = [
    "parse_timecode",
    "format_timecode",
    "download",
    "trim",
    "download_and_trim",
    "TrimRange",
]


# --------------------------------------------------------------------------- #
# 시간 표기(timecode) 처리
# --------------------------------------------------------------------------- #
def parse_timecode(value) -> float:
    """timecode 문자열을 초(second) 단위 float 로 변환합니다.

    허용 형식:
        "90", "90.5"        -> 초
        "01:30"             -> 분:초
        "01:02:03"          -> 시:분:초
        90, 90.5 (숫자)     -> 그대로 초로 사용
    """
    if isinstance(value, (int, float)):
        seconds = float(value)
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("빈 timecode 는 사용할 수 없습니다.")
        parts = text.split(":")
        if len(parts) > 3:
            raise ValueError(f"잘못된 timecode 형식입니다: {value!r}")
        try:
            numbers = [float(p) for p in parts]
        except ValueError as exc:
            raise ValueError(f"잘못된 timecode 형식입니다: {value!r}") from exc
        seconds = 0.0
        for number in numbers:  # [시, 분, 초] 순서로 60진법 누적
            seconds = seconds * 60 + number
    if seconds < 0:
        raise ValueError(f"timecode 는 음수가 될 수 없습니다: {value!r}")
    return seconds


def format_timecode(seconds: float) -> str:
    """초 단위 float 를 ``HH:MM:SS.mmm`` 문자열로 변환합니다 (ffmpeg 입력용)."""
    if seconds < 0:
        raise ValueError("timecode 는 음수가 될 수 없습니다.")
    hours, remainder = divmod(int(seconds), 3600)
    minutes, whole_seconds = divmod(remainder, 60)
    milliseconds = round((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


@dataclass
class TrimRange:
    """자를 구간(시작~끝)을 나타냅니다."""

    start: float
    end: float

    @classmethod
    def from_strings(cls, start, end) -> "TrimRange":
        start_s = parse_timecode(start)
        end_s = parse_timecode(end)
        if end_s <= start_s:
            raise ValueError(
                f"끝 시간({end})은 시작 시간({start})보다 뒤여야 합니다."
            )
        return cls(start=start_s, end=end_s)

    @property
    def duration(self) -> float:
        return self.end - self.start


# --------------------------------------------------------------------------- #
# 외부 의존성 확인
# --------------------------------------------------------------------------- #
def _find_ffmpeg() -> Optional[str]:
    """ffmpeg 실행 파일 경로를 찾습니다.

    1) PATH 에 설치된 시스템 ffmpeg 를 우선 사용.
    2) 없으면 ``imageio-ffmpeg`` 가 제공하는 번들 바이너리를 사용
       (``pip install imageio-ffmpeg`` 만으로 동작 가능).
    찾지 못하면 None.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg  # noqa: WPS433

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 (미설치/조회 실패 시 무시)
        return None


def _require_ffmpeg() -> str:
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg 를 찾을 수 없습니다. 아래 중 하나로 설치 후 다시 시도하세요.\n"
            "  pip:            pip install imageio-ffmpeg   (설치 불필요, 가장 간편)\n"
            "  macOS:          brew install ffmpeg\n"
            "  Ubuntu/Debian:  sudo apt install ffmpeg\n"
            "  Colab:          !apt -qq install ffmpeg"
        )
    return ffmpeg


def _import_yt_dlp():
    try:
        import yt_dlp  # noqa: WPS433 (지연 import: 의존성 없이도 모듈 로드 가능)
    except ImportError as exc:
        raise RuntimeError(
            "yt-dlp 가 설치되어 있지 않습니다. `pip install yt-dlp` 후 다시 시도하세요."
        ) from exc
    return yt_dlp


# --------------------------------------------------------------------------- #
# 다운로드
# --------------------------------------------------------------------------- #
def download(
    url: str,
    output_dir: str = "downloads",
    *,
    audio_only: bool = False,
    resolution: Optional[int] = None,
    cookies: Optional[str] = None,
    quiet: bool = False,
) -> str:
    """``url`` 의 YouTube 영상을 내려받고 저장된 파일 경로를 반환합니다.

    Args:
        url: YouTube 영상 URL.
        output_dir: 저장 폴더 (없으면 생성).
        audio_only: True 면 오디오(mp3)만 추출.
        resolution: 최대 세로 해상도(px). 예: 1080, 720. None 이면 최고 화질.
        cookies: 로그인/연령 제한 영상용 cookies.txt 경로 (선택).
        quiet: True 면 yt-dlp 진행 로그를 숨김.

    Returns:
        내려받은 파일의 절대 경로.
    """
    yt_dlp = _import_yt_dlp()
    os.makedirs(output_dir, exist_ok=True)

    outtmpl = os.path.join(output_dir, "%(title)s [%(id)s].%(ext)s")
    ydl_opts: dict = {
        "outtmpl": outtmpl,
        "quiet": quiet,
        "noprogress": quiet,
        "restrictfilenames": False,
    }

    # 영상+오디오 병합 / 오디오 추출에 ffmpeg 가 필요합니다.
    # 시스템 ffmpeg 가 없으면 imageio-ffmpeg 번들 바이너리를 사용합니다.
    ffmpeg_path = _find_ffmpeg()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    if audio_only:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        if resolution:
            ydl_opts["format"] = (
                f"bestvideo[height<={resolution}]+bestaudio/"
                f"best[height<={resolution}]/best"
            )
        else:
            ydl_opts["format"] = "bestvideo*+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"

    if cookies:
        if not os.path.isfile(cookies):
            raise FileNotFoundError(f"쿠키 파일을 찾을 수 없습니다: {cookies}")
        ydl_opts["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # yt-dlp 최신 버전은 실제 저장 경로를 requested_downloads 에 담아 줍니다.
    requested = (info or {}).get("requested_downloads")
    if requested:
        filepath = requested[0].get("filepath")
        if filepath:
            return os.path.abspath(filepath)

    # 후처리(병합/추출)로 확장자가 바뀐 경우를 보정합니다.
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        guessed = ydl.prepare_filename(info)
    if audio_only:
        guessed = os.path.splitext(guessed)[0] + ".mp3"
    elif not guessed.endswith(".mp4"):
        mp4_guess = os.path.splitext(guessed)[0] + ".mp4"
        if os.path.isfile(mp4_guess):
            guessed = mp4_guess
    return os.path.abspath(guessed)


# --------------------------------------------------------------------------- #
# 구간 자르기 (길이 편집)
# --------------------------------------------------------------------------- #
def trim(
    input_path: str,
    start,
    end,
    output_path: Optional[str] = None,
    *,
    copy: bool = False,
    quiet: bool = False,
) -> str:
    """``input_path`` 영상에서 ``start``~``end`` 구간만 잘라 저장합니다.

    Args:
        input_path: 원본 영상 경로.
        start: 시작 시간 (예: "00:30", 30, "0:00:30").
        end: 끝 시간 (예: "01:45").
        output_path: 저장 경로. None 이면 ``<원본>_clip<ext>`` 로 자동 지정.
        copy: True 면 재인코딩 없이 스트림 복사(-c copy). 매우 빠르지만
            키프레임 단위로만 잘려 시작점이 약간 어긋날 수 있음.
            False(기본)면 재인코딩하여 프레임 단위로 정확히 자름.
        quiet: True 면 ffmpeg 로그를 숨김.

    Returns:
        잘린 영상 파일의 절대 경로.
    """
    ffmpeg = _require_ffmpeg()
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {input_path}")

    clip = TrimRange.from_strings(start, end)

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_clip{ext or '.mp4'}"

    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)

    # -ss 를 -i 앞에 두어 빠르게 탐색하고, -t(길이)로 정확한 구간을 지정합니다.
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        format_timecode(clip.start),
        "-i",
        input_path,
        "-t",
        format_timecode(clip.duration),
    ]
    if copy:
        cmd += ["-c", "copy"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
    cmd += ["-movflags", "+faststart", output_path]

    if quiet:
        cmd[1:1] = ["-loglevel", "error"]

    subprocess.run(cmd, check=True)
    return os.path.abspath(output_path)


# --------------------------------------------------------------------------- #
# 다운로드 + 구간 자르기 (한 번에)
# --------------------------------------------------------------------------- #
def download_and_trim(
    url: str,
    start,
    end,
    output_dir: str = "downloads",
    *,
    output_path: Optional[str] = None,
    keep_full: bool = False,
    resolution: Optional[int] = None,
    cookies: Optional[str] = None,
    copy: bool = False,
    quiet: bool = False,
) -> str:
    """영상을 내려받은 뒤 ``start``~``end`` 구간만 잘라 반환합니다.

    Args:
        keep_full: True 면 원본(전체) 파일을 남기고, False 면 잘라낸 뒤 삭제.
        (그 외 인자는 download / trim 과 동일)

    Returns:
        잘린 영상 파일의 절대 경로.
    """
    full_path = download(
        url,
        output_dir=output_dir,
        resolution=resolution,
        cookies=cookies,
        quiet=quiet,
    )
    clipped = trim(
        full_path,
        start,
        end,
        output_path=output_path,
        copy=copy,
        quiet=quiet,
    )
    if not keep_full and os.path.abspath(full_path) != os.path.abspath(clipped):
        try:
            os.remove(full_path)
        except OSError:
            pass
    return clipped


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube_downloader",
        description="YouTube 영상을 다운로드하고 시작~끝 구간을 잘라냅니다.",
    )
    parser.add_argument("url", help="YouTube 영상 URL")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="downloads",
        help="저장 폴더 (기본: downloads)",
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        default=None,
        help="결과 파일 경로 (미지정 시 자동)",
    )
    parser.add_argument(
        "-s",
        "--start",
        default=None,
        help="자르기 시작 시간 (예: 00:30). --end 와 함께 지정.",
    )
    parser.add_argument(
        "-e",
        "--end",
        default=None,
        help="자르기 끝 시간 (예: 01:45). --start 와 함께 지정.",
    )
    parser.add_argument(
        "--keep-full",
        action="store_true",
        help="구간을 자른 뒤에도 원본(전체) 파일을 남깁니다.",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        default=None,
        help="최대 세로 해상도(px). 예: 1080, 720 (기본: 최고 화질)",
    )
    parser.add_argument(
        "--cookies",
        default=None,
        help="연령 제한/로그인 영상용 cookies.txt 경로",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="재인코딩 없이 빠르게 자르기 (키프레임 단위, 시작점이 약간 어긋날 수 있음)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="진행 로그 숨김",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)

    has_start = args.start is not None
    has_end = args.end is not None
    if has_start != has_end:
        print("오류: --start 와 --end 는 함께 지정해야 합니다.", file=sys.stderr)
        return 2

    try:
        if has_start and has_end:
            result = download_and_trim(
                args.url,
                args.start,
                args.end,
                output_dir=args.output_dir,
                output_path=args.output_path,
                keep_full=args.keep_full,
                resolution=args.resolution,
                cookies=args.cookies,
                copy=args.copy,
                quiet=args.quiet,
            )
            print(f"완료 (구간 자르기): {result}")
        else:
            result = download(
                args.url,
                output_dir=args.output_dir,
                resolution=args.resolution,
                cookies=args.cookies,
                quiet=args.quiet,
            )
            print(f"완료 (다운로드): {result}")
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"ffmpeg 실행 실패 (종료 코드 {exc.returncode})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
