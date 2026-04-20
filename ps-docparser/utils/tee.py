"""stdout을 파일과 콘솔에 동시 출력한다. (main.py _Tee 추출)"""


class Tee:
    """stdout을 파일과 콘솔에 동시 출력한다."""

    def __init__(self, *files):
        self.files = files

    def write(self, obj):
        for f in self.files:
            try:
                f.write(obj)
                f.flush()
            except UnicodeEncodeError:
                # Why: Windows CP949 콘솔은 BMP 외 문자를 처리 못한다.
                #      배치 중단 방지를 위해 콘솔만 '?'로 치환, 로그는 원본 유지.
                enc = getattr(f, "encoding", "utf-8") or "utf-8"
                safe = obj.encode(enc, errors="replace").decode(enc)
                f.write(safe)
                f.flush()

    def flush(self):
        for f in self.files:
            f.flush()
