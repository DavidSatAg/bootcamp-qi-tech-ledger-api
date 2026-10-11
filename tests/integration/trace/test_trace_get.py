from uuid import uuid4

from tests.utils import RequestGenerator


class TestTraceGet:
    def test_transfers_trace_unknown_returns_404(self):
        unknown_key = str(uuid4())

        status, response = RequestGenerator.GET_transfer_trace(unknown_key)

        assert status == 404, response
        assert response["code"] == "QIT001020"
