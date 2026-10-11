from uuid import uuid4

from tests.utils import RequestGenerator


class TestStatementGet:
    def test_statement_get_unknown_returns_404(self):
        status, response = RequestGenerator.GET_statement(str(uuid4()))

        assert status == 404, response
        assert response["code"] == "QIT001022"
