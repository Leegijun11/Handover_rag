# -*- coding: utf-8 -*-
"""pytest 공용 설정 (guidelines 5-10, 담당: 조장).

backend/ 바깥(레포 루트)에서 pytest를 실행해도 `from routers.document import ...`
같은 import가 되도록 backend/를 sys.path에 넣어준다 — scripts/seed_local.py가 쓰는
것과 같은 패턴이다. 테스트 파일 각각에 이 코드를 반복해서 넣지 않도록 conftest.py에
한 번만 둔다 (pytest가 테스트를 수집하기 전에 자동으로 로드하는 파일).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
