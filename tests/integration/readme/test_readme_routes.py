import re
import shlex
from pathlib import Path
from uuid import uuid4

from tests.utils import RequestGenerator

README = Path(__file__).resolve().parents[3] / "README.md"
README_BASE_URL = "http://localhost:3003"
NAME = re.compile(r"\$([A-Z][A-Z0-9_]*)")
ROUTE_ROW = re.compile(r"^\|\s*`([A-Z]+)`\s*\|\s*`(/[^`]*)`")

# As rotas do Ledger (spec 16 §7, R16): as das fatias 04 a 13 e 15a.
R16 = [
    ("POST", "/contract_ledgers"),
    ("POST", "/contract_ledgers/{contract_key}/closure"),
    ("GET", "/ledger_accounts/{ledger_account_key}"),
    ("GET", "/ledger_accounts"),
    ("POST", "/transfers/inflow"),
    ("POST", "/transfers/split"),
    ("POST", "/transfers/payout"),
    ("POST", "/wallets"),
    ("POST", "/webhooks/provider"),
    ("GET", "/transfers/{ledger_transaction_key}/trace"),
    ("POST", "/transfers/{ledger_transaction_key}/reversal"),
    ("GET", "/integrity"),
    ("POST", "/transfers/internal"),
    ("POST", "/statement"),
    ("GET", "/statement/{statement_key}"),
    ("POST", "/statement/verify"),
]

# As da fatia 14 (R14): entram quando a API as tiver.
R14 = [
    ("PUT", "/ledger_accounts/{ledger_account_key}/status"),
    ("GET", "/transfers"),
    ("POST", "/outbox/dispatch"),
]


def section_11() -> str:
    """O texto da seção 11 do README, até a próxima seção de nível 2."""
    lines = README.read_text(encoding="utf-8").splitlines()
    inside = False
    section = []
    for line in lines:
        if line.startswith("## "):
            inside = line.startswith("## 11.")
            continue
        if inside:
            section.append(line)

    return "\n".join(section)


def curl_lines() -> list:
    """Cada `curl` dos blocos `bash` da seção 11, com as linhas que acabam
    em `\\` juntadas à seguinte."""
    commands = []
    for block in re.findall(r"```bash\n(.*?)```", section_11(), flags=re.DOTALL):
        joined = re.sub(r"\\\n", " ", block)
        commands.extend(line.strip() for line in joined.splitlines() if line.strip().startswith("curl "))

    return commands


def parse_curl(command: str) -> dict:
    """Desmonta o `curl`: verbo, URL, cabeçalhos e corpo."""
    tokens = shlex.split(command)
    parsed = {"method": "GET", "url": None, "headers": {}, "body": None}
    position = 1
    while position < len(tokens):
        token = tokens[position]
        if token == "-X":
            position += 1
            parsed["method"] = tokens[position]
        elif token == "-H":
            position += 1
            name, value = tokens[position].split(":", 1)
            parsed["headers"][name.strip()] = value.strip()
        elif token in ("-d", "--data", "--data-raw"):
            position += 1
            parsed["body"] = tokens[position]
        elif token.startswith("http"):
            parsed["url"] = token
        position += 1

    return parsed


def path_of(url: str) -> str:
    assert url.startswith(README_BASE_URL), url

    return url[len(README_BASE_URL):]


def route_pattern(route_path: str) -> re.Pattern:
    """O caminho da rota como regex: cada `{param}` vale um segmento."""
    return re.compile("^" + re.sub(r"\\\{[a-z_]+\\\}", "[^/]+", re.escape(route_path)) + "$")


def existing_routes() -> list:
    """R16 e as de R14 que a API já atende (resposta fora de QIT000404/405)."""
    routes = list(R16)
    for method, route_path in R14:
        probe = route_path.replace("{ledger_account_key}", str(uuid4()))
        _status, response = RequestGenerator.send_readme_curl(method, probe, {"INTERNAL-TOKEN": "default_token"})
        if not (isinstance(response, dict) and response.get("code") in ("QIT000404", "QIT000405")):
            routes.append((method, route_path))

    return routes


class TestReadmeRoutes:
    def test_readme_curls_reach_existing_routes(self):
        commands = curl_lines()
        assert len(commands) >= 16, commands
        values = {}

        for command in commands:
            filled = NAME.sub(lambda match: values.setdefault(match.group(1), str(uuid4())), command)
            curl = parse_curl(filled)
            raw_body = None
            if curl["body"] is not None:
                # O curl do Git Bash manda o corpo na página de código do
                # terminal, não em UTF-8: acento no `-d` chega quebrado à API.
                assert curl["body"].isascii(), (command, "corpo com caractere fora do ASCII")
                raw_body = curl["body"].encode("utf-8")

            status, response = RequestGenerator.send_readme_curl(
                curl["method"], path_of(curl["url"]), curl["headers"], raw_body
            )

            assert status < 500 or (status == 503 and response["code"] == "QIT001040"), (command, status, response)
            assert status not in (400, 403, 405), (command, status, response)
            if isinstance(response, dict):
                assert response.get("code") != "QIT000404", (command, response)

    def test_readme_covers_every_ledger_route(self):
        table = set()
        for line in section_11().splitlines():
            match = ROUTE_ROW.match(line)
            if match:
                table.add((match.group(1), match.group(2)))
        curls = [parse_curl(command) for command in curl_lines()]

        for method, route_path in existing_routes():
            assert (method, route_path) in table, (method, route_path)
            pattern = route_pattern(route_path)
            matching = [
                curl
                for curl in curls
                if curl["method"] == method and pattern.match(path_of(curl["url"]).split("?")[0])
            ]
            assert matching, (method, route_path)
