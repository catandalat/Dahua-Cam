"""Dahua HTTP CGI client: Digest auth, event attach, multipart parsing."""

from dahua_client.client import DahuaClient
from dahua_client.kv_parser import kv_lines_to_dict
from dahua_client.multipart import MultipartEvent, parse_multipart_stream

__all__ = [
    "DahuaClient",
    "kv_lines_to_dict",
    "MultipartEvent",
    "parse_multipart_stream",
]
