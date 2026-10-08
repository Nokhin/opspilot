"""Remove machine identifiers and normalize timezone-aware JUnit timestamps."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def sanitize_junit(path: Path) -> None:
    tree = ET.parse(path)
    for element in tree.iter():
        element.attrib.pop("hostname", None)
        if "timestamp" in element.attrib:
            timestamp = datetime.fromisoformat(element.attrib["timestamp"])
            if timestamp.tzinfo is None:
                element.attrib.pop("timestamp")
            else:
                element.attrib["timestamp"] = (
                    timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
                )
    tree.write(path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    sanitize_junit(parser.parse_args().path)


if __name__ == "__main__":
    main()
