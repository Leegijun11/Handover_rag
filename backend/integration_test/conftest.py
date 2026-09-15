# -*- coding: utf-8 -*-
"""pytest 공용 설정 (guidelines 5-10, 담당: 조장).

unit_test/conftest.py와 같은 이유 — backend/ 바깥에서 pytest를 실행해도
`from main import app` 같은 import가 되도록 backend/를 sys.path에 넣어준다.

unit_test/와 다른 점: 여기 있는 테스트들은 DB를 mock하지 않고 실제 로컬 MySQL에
그대로 연결한다(.env 설정 그대로) — 별도 테스트 DB를 새로 준비하는 건 이 프로젝트
규모에서 불필요하다고 판단함(CI 자동화 없음, 개발자별로 로컬 DB를 따로 씀). 대신
OpenAI처럼 실제로 돈이 드는 외부 API 호출은 unit_test와 동일하게 monkeypatch로
가짜 처리한다. 테스트 데이터는 매번 고유한 이메일/이름으로 만들어서(uuid) 실행할
때마다 충돌 없이 반복 가능하게 한다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


@pytest.fixture
def client():
    """실제 앱(main.app)을 그대로 감싼 테스트 클라이언트. 서버를 따로 띄우지 않고도
    라우팅·인증·DB 조회까지 진짜 코드 경로 그대로 태운다."""
    return TestClient(app)
