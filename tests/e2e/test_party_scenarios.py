from tests.utils.db_utils import DbUtils
from tests.utils.party_scenarios import APROVADA, PENDENTE, SCENARIOS, GET_party, seed_party_scenarios
from tests.utils.request_generator import RequestGenerator


class TestPartyScenarios:
    def test_seed_reproduces_each_magic_key(self, party_scenarios):
        """Cada papel volta do `GET /parties` do Cadastro como a chave mágica
        voltava do party-mock (guia 00 §2): o mesmo status e a pix_key
        mandada no cadastro — null na `sem_pix`, como na `dddd…`."""
        print("\nparty_key reais desta rodada:")
        for role, party_key in party_scenarios.items():
            print(f"  {role:<12} {party_key}")

        assert set(party_scenarios) == set(SCENARIOS)

        for role, (_ending, pix_key, expected_status) in SCENARIOS.items():
            status, response = GET_party(party_scenarios[role])

            assert status == 200, (role, response)
            assert response["party_type"] == "individual", (role, response)
            assert response["status"] == expected_status, (role, response)
            assert response["pix_key"] == pix_key, (role, response)

    def test_seed_twice_returns_same_keys(self, party_scenarios):
        """PAR-12: a semeadura roda de novo contra um Cadastro que já tem as
        partes. Os documentos são fixos; o `409 QIT002003` do segundo
        `POST /parties` vira a busca por documento, e as chaves são as
        mesmas da primeira vez."""
        assert seed_party_scenarios() == party_scenarios

    def test_ledger_reads_seeded_parties_from_real_party_api(self, party_scenarios):
        """O Ledger enxerga as mesmas partes: a aprovada abre carteira, e a
        pendente é recusada como a `aaaa…` era (409 QIT001038). Se o Ledger
        ainda apontasse para o party-mock, a aprovada também daria 409 —
        o mock não conhece a chave e devolve 404.

        O banco do Ledger é zerado antes: as chaves se repetem entre rodadas
        (PAR-12), e a carteira aberta numa rodada anterior voltaria `200`."""
        DbUtils.rollback()

        status, response = RequestGenerator.POST_wallets({"party_key": party_scenarios[APROVADA], "actor": "ledger-e2e"})
        assert status == 201, response

        status, response = RequestGenerator.POST_wallets({"party_key": party_scenarios[PENDENTE], "actor": "ledger-e2e"})
        assert status == 409, response
        assert response["code"] == "QIT001038", response
