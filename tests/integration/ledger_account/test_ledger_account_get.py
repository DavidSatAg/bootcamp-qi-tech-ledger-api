from uuid import uuid4

from tests.utils import RequestGenerator


class TestLedgerAccountGet:
    def test_ledger_accounts_get_unknown_returns_404(self):
        unknown_key = str(uuid4())

        status, response = RequestGenerator.GET_ledger_account(unknown_key)

        assert status == 404
        assert response["code"] == "QIT001018"
