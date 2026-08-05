# -*- coding: utf-8 -*-
"""youtube_downloader 패키지.

YouTube 영상 다운로드 및 구간 자르기(길이 편집) 기능을 제공합니다.
"""

from .youtube_downloader import (
    TrimRange,
    download,
    download_and_trim,
    format_timecode,
    parse_timecode,
    trim,
)

__all__ = [
    "TrimRange",
    "download",
    "download_and_trim",
    "format_timecode",
    "parse_timecode",
    "trim",
]
