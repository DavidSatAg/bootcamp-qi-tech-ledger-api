# Bootcamp QI Tech — projeto base da API

Projeto base do Bootcamp: uma API REST em **Python + FastAPI**, com banco
**PostgreSQL**, rodando em **Docker**.

Você não precisa saber programar para começar. A API e o banco sobem
no **Docker**, então você não instala nem um nem outro na sua máquina.
Os **testes** rodam no seu Python — são dois comandos, e a seção 2
mostra os dois.

---

## 0. O que você precisa ter instalado

São três coisas.

| O quê | Para quê | Como conferir |
|---|---|---|
| **Docker** (com o Docker Desktop no Mac/Windows) | roda a API e o banco | `docker compose version` |
| **Git** | trazer o projeto para o seu computador | `git --version` |
| **Python 3.11 ou mais novo** | rodar os testes (seção 2) | `python3 --version` |

Abra o terminal e rode os três comandos da coluna da direita. Se todos
responderem um número de versão, você está pronto.

> **Por que o Python, se tudo roda no Docker?** Porque os testes rodam
> FORA dele, na sua máquina, contra a API que está de pé no container.
> O ganho é o ciclo: você salva um teste e roda na hora, sem esperar
> imagem nenhuma ser montada. O preço está explicado na seção 2.

> **`docker compose version` deu erro?** Sua instalação do Docker é
> antiga demais (ou o Docker não está ligado). No Mac e no Windows,
> abra o **Docker Desktop** e espere a baleia parar de se mexer. Se o
> comando continuar falhando, reinstale pelo site oficial —
> o `docker compose` (com **espaço**) vem junto desde 2022.

Nada além destes três. Se em algum momento este projeto pedir que você
instale outro PROGRAMA, é um bug do projeto — avise a gente. (As
bibliotecas Python que os testes usam são outra conversa: elas entram
com um `pip install` na seção 2, dentro de uma pasta do próprio
projeto, e somem quando você apaga essa pasta.)

---

## 1. Rodando pela primeira vez

```bash
docker compose up
```

Um comando. Só isso, e não precisa criar nem copiar arquivo nenhum
antes: as configurações já vêm com valor padrão dentro do
`docker-compose.yml`.

O Docker baixa o Python, sobe o banco, cria as tabelas e liga a API. Na
primeira vez demora alguns minutos; depois é quase instantâneo.

São duas coisas de pé, e vale saber o nome de cada uma:

| Serviço | O que é |
|---|---|
| `api` | a API que responde às suas requisições |
| `db` | o banco de dados (PostgreSQL) |

Quando aparecer `Application startup complete`, a API está no ar. Abra
no navegador:

### 👉 http://localhost:3000

Você vai ver isto:

```json
{"service":"bootcamp-api","id":"8"}
```

Pouca coisa, e de propósito: essa rota só diz "estou viva, e eu sou este
serviço". Mas você acabou de fazer uma **requisição HTTP** — a mesma
coisa que o navegador faz ao abrir qualquer site.

### Agora as outras rotas

Elas não abrem no navegador, porque exigem um cabeçalho: o
`INTERNAL-TOKEN`, que é a senha da API (seção 6). Para mandar um
cabeçalho a gente usa o `curl`, um programa de linha de comando que já
vem instalado no Mac, no Linux e no Windows.

**Abra um segundo terminal** — o primeiro está ocupado rodando a API — e
cole um comando de cada vez.

> **No Windows**, use o **Git Bash**: ele veio junto com o Git da seção
> 0. No PowerShell estes comandos não funcionam, porque lá `curl` é o
> apelido de outro programa, com outra sintaxe.

#### 1. Criar uma entidade

```bash
curl -X POST http://localhost:3000/sample_entity \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{
    "hello": "world",
    "name": "Maria da Silva",
    "email": "maria.silva@exemplo.com.br",
    "document_number": "529.982.247-25",
    "birthdate": "1990-05-17"
  }'
```

```json
{"sample_entity_key":"3fbf83e9-e5fc-4e0f-8427-db6a1a50f964"}
```

Esse `sample_entity_key` é o endereço da entidade que você acabou de
criar. **Copie o seu** — ele nasce diferente a cada vez, e nos comandos
abaixo você troca o que está escrito aqui pelo seu.

> **Rodou o comando duas vezes e levou 409 na segunda?** É de propósito:
> o CPF e o e-mail não podem se repetir. Para criar uma segunda
> entidade, troque o e-mail (qualquer um serve) e o CPF — mas o CPF tem
> que ser **válido de verdade**, com os dois dígitos finais batendo com
> a conta. O `529.982.247-25` acima é um CPF de teste conhecido, que
> passa na conta e não pertence a ninguém.
>
> **E os cinco campos são todos obrigatórios?** São. Mande `{}` e a API
> diz qual está faltando — é o comando 6 lá embaixo.

#### 2. Buscar a entidade

```bash
curl http://localhost:3000/sample_entity/3fbf83e9-e5fc-4e0f-8427-db6a1a50f964 \
  -H "INTERNAL-TOKEN: default_token"
```

```json
{"hello":"world","sample_entity_key":"3fbf83e9-e5fc-4e0f-8427-db6a1a50f964","name":"Maria da Silva","email":"maria.silva@exemplo.com.br","document_number":"529.982.247-25","birthdate":"1990-05-17","status":"pending","counter":0,"status_events":[{"status":"pending","event_datetime":"2026-09-11T20:36:43.104210"}]}
```

Você mandou cinco campos e voltaram nove. Os quatro extras a API montou
sozinha:

- **`sample_entity_key`** — o endereço da entidade;
- **`status`** — o estado inicial, `pending`;
- **`counter`** — um contador zerado;
- **`status_events`** — a **história**. Cada vez que o status muda, uma
  linha nova entra aqui, com a hora. Saber onde a entidade está é uma
  coisa; saber por onde ela passou é outra, e é essa lista que responde
  a segunda.

#### 3. Listar as entidades

```bash
curl http://localhost:3000/sample_entities \
  -H "INTERNAL-TOKEN: default_token"
```

```json
{"data":[{"hello":"world","sample_entity_key":"3fbf83e9-e5fc-4e0f-8427-db6a1a50f964","name":"Maria da Silva","email":"maria.silva@exemplo.com.br","document_number":"529.982.247-25","birthdate":"1990-05-17","status":"pending","counter":0}],"limit":10,"page":0,"is_last_page":true}
```

Vêm de dez em dez, da mais nova para a mais antiga. Para pedir outra
quantidade ou outra página, acrescente `?limit=2&page=0` ao endereço —
o `limit` vai até **100**. O `is_last_page` já responde a pergunta
seguinte — "tem mais?" — sem custar uma segunda requisição.

Repare no que **não** veio: o `status_events`. Na lista cada item vem
resumido, porque montar a história de cada entidade custa uma consulta a
mais por item — numa página de 100, são 100 consultas para uma
informação que quem está varrendo não pediu. A história aparece quando
você abre UMA entidade, no comando 2.

Também dá para **filtrar**. Todos os filtros se combinam, e todos são
opcionais:

```bash
curl "http://localhost:3000/sample_entities?name=maria&status=pending&status=failed" \
  -H "INTERNAL-TOKEN: default_token"
```

| Filtro | Como casa |
|---|---|
| `name` | por **pedaço**, ignorando maiúscula/minúscula |
| `email` | exato |
| `document_number` | exato |
| `birthdate_from` / `birthdate_to` | intervalo, **incluindo** as duas pontas |
| `status` | pode repetir: `?status=pending&status=failed` traz os dois |

Repare que `status` se comporta ao contrário dos outros: `name` junto
com `email` **estreita** a busca (os dois precisam bater), mas dois
`status` **alargam** (basta um bater). Faz sentido pelo que a pessoa
quer dizer — "me mostra o que deu errado e o que deu certo" é um pedido
legítimo, e uma entidade só pode estar num dos baldes.

#### 4. Somar 1 no contador

```bash
curl -i -X PUT http://localhost:3000/webhook/sample_entity/3fbf83e9-e5fc-4e0f-8427-db6a1a50f964/increment_counter \
  -H "INTERNAL-TOKEN: default_token"
```

```
HTTP/1.1 204 No Content
```

Esta rota não responde nada — por isso o `-i`, que manda o `curl`
mostrar também o **status** da resposta. `204` quer dizer "deu certo e
não tenho nada a dizer". Repita o comando 2: o `counter` agora é `1`.

#### 5. Mudar o status

```bash
curl -X PUT http://localhost:3000/sample_entity/3fbf83e9-e5fc-4e0f-8427-db6a1a50f964 \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{"status": "success"}'
```

```json
{"sample_entity_key":"3fbf83e9-e5fc-4e0f-8427-db6a1a50f964"}
```

Repita o comando 2: o `status` virou `success`. E rode este comando 5
mais uma vez — agora a API recusa:

```json
{"title":"Entity cannot change status","description":"Entity with status success cannot update to success.","translation":"Essa entidade não pode ser atualizada.","code":"QIT001002"}
```

Isso é uma **regra de negócio**, não um erro de digitação: entidade que
já terminou não volta atrás. A frase que decide isso mora em
`src/controllers/sample_entity_controller.py`, e você pode ir ler.

#### 6. Mandar um JSON torto

```bash
curl -X POST http://localhost:3000/sample_entity \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{}'
```

```json
{"title":"Bad Request","description":"'hello' is a required property","translation":"Payload Inválido","code":"QIT000001"}
```

**400**, e nada foi criado. O `hello` é obrigatório, e quem recusou não
foi a regra de negócio: foi o `src/schemas/`, antes da primeira linha da
rota rodar. Pedido torto não chega a custar uma consulta ao banco.

Repare que ele reclamou de **um** campo, e você deixou cinco de fora. É
assim mesmo: a validação para no primeiro problema. Tire o `{}` e vá
preenchendo um campo de cada vez para ver a reclamação andar.

E existe uma fronteira aqui que vale a pena enxergar cedo. Mande um CPF
com o formato certo e os dígitos errados:

```bash
curl -X POST http://localhost:3000/sample_entity \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{
    "hello": "world",
    "name": "Maria da Silva",
    "email": "outra@exemplo.com.br",
    "document_number": "111.111.111-11",
    "birthdate": "1990-05-17"
  }'
```

```json
{"title":"Invalid Document Number","description":"The document number 111.111.111-11 is not a valid CPF.","translation":"O CPF informado não é válido.","code":"QIT001003"}
```

Agora é **422**, não 400. A diferença não é capricho: 400 quer dizer
"não consegui ler o seu pedido"; 422 quer dizer "li, entendi, e esse
valor não pode existir". O schema sabe contar pontos e traços — ele não
sabe fazer a conta dos dois últimos dígitos. Quem sabe é o
`src/utils/document_number.py`, e por isso essa recusa vem de dentro,
com código próprio.

#### Esqueceu o `-H "INTERNAL-TOKEN: ..."`?

A API responde **403** e nem chega a olhar o resto:

```json
{"title":"Forbidden","description":"Request must be internal","translation":"Requisição precisa ser interna","code":"QIT000002"}
```

#### Toda resposta vem com um número de protocolo

Repare no `-i` deste comando: ele mostra os **cabeçalhos** da resposta,
não só o corpo.

```bash
curl -i "http://localhost:3000/sample_entities?limit=1" \
  -H "INTERNAL-TOKEN: default_token"
```

```
HTTP/1.1 200 OK
content-type: application/json
x-request-id: 8f3c1e42-1b0d-4f77-9a55-2e4c9d1f0abc
...
```

Esse `x-request-id` é o **número de protocolo** da sua requisição: um
nome único, criado no instante em que ela chegou. Copie o seu e procure
por ele no log:

```bash
docker compose logs api | grep 8f3c1e42
```

```
[INFO] bootcamp-api.middlewares.request_logger [8f3c1e42-...] - ENTROU GET /sample_entities?limit=1
[INFO] bootcamp-api.middlewares.request_logger [8f3c1e42-...] - SAIU 200 GET /sample_entities - 2.9 ms
```

Duas linhas, o mesmo nome nas duas — e nenhuma outra requisição usa esse
nome. Serve para o dia em que alguém disser "deu erro por volta das
14h30": sem o número, você abre o log e encontra mil linhas parecidas, de
mil requisições diferentes, embaralhadas, porque a API atende várias ao
mesmo tempo e o log é um só. Com o número, achar a agulha é um `grep`.

Se quem chamou já mandar um `x-request-id`, a API **respeita o que veio**
e usa o mesmo — é assim que se segue um único pedido atravessando vários
sistemas:

```bash
curl -i "http://localhost:3000/sample_entities?limit=1" \
  -H "INTERNAL-TOKEN: default_token" \
  -H "X-Request-ID: meu-teste-1"
```

Experimente mandar um valor esquisito nesse cabeçalho — com espaços, ou
bem comprido. A API não devolve o que você mandou: ela troca por um novo.
O porquê está em `src/utils/request_context.py`, e é uma das poucas
lições de segurança que cabem em cinco linhas.

> Só o `/` e o `/health_check` não aparecem no log: o Docker consulta o
> health check a cada três segundos, e sem essa exceção o log seria
> quase só isso. Eles ganham o `x-request-id` como todo mundo — o que
> não ganham é a linha de log.

### Todas as rotas

Sete endereços — este é o mapa inteiro da API:

| Método e rota | O que faz | Responde |
|---|---|---|
| `GET /` | diz qual serviço é este | `200` + nome e id |
| `GET /health_check` | diz se a API está de pé | `204`, sem corpo |
| `POST /sample_entity` | cria uma entidade | `201` + o `sample_entity_key` |
| `GET /sample_entity/{key}` | busca uma entidade | `200` + a entidade |
| `GET /sample_entities` | lista, de dez em dez, com filtros | `200` + a página |
| `PUT /sample_entity/{key}` | muda o status (`success` ou `failed`) | `202` + o `sample_entity_key` |
| `PUT /webhook/sample_entity/{key}/increment_counter` | soma 1 no contador | `204`, sem corpo |

As cinco de baixo exigem o `INTERNAL-TOKEN` (seção 6). As duas de cima
são abertas — a primeira você já usou: foi ela que respondeu no
navegador.

Os parâmetros da listagem, todos opcionais e combináveis:
`?limit=` (padrão 10, teto 100) · `?page=` (padrão 0) · `?status=`
(repetível) · `?name=` · `?email=` · `?document_number=` ·
`?birthdate_from=` · `?birthdate_to=`. Qualquer outro nome a API
**recusa** com 400 — é o `src/schemas/get_sample_entities.json` que
decide, e ele não aceita o que não conhece. Vale a pena errar de
propósito uma vez:

```bash
curl "http://localhost:3000/sample_entities?stauts=pending" \
  -H "INTERNAL-TOKEN: default_token"
```

Sem essa recusa, um `stauts` com a letra trocada viraria uma lista
inteira devolvida como se o filtro tivesse funcionado — o pior tipo de
bug, o que não reclama.

Para desligar tudo: `Ctrl+C` no terminal da API e depois

```bash
docker compose down
```

---

## 2. Rodando os testes

Os testes rodam **na sua máquina**, contra a API que está de pé no
Docker. Então são dois passos: um de uma vez só, outro toda vez.

**Uma vez só — instalar as dependências de teste:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

O `.venv` é uma pasta com um Python só deste projeto. Ele existe pra que
instalar algo aqui não mexa no Python da sua máquina — e pra que apagar a
pasta desfaça tudo. No Windows, a segunda linha é
`.venv\Scripts\activate`.

**Toda vez — com a API de pé, em outro terminal:**

```bash
pytest
```

A API precisa estar respondendo antes. Se você acabou de dar
`docker compose up`, espere o `(healthy)` aparecer — é o healthcheck do
`docker-compose.yml` dizendo que a porta já atende. Sem isso, o primeiro
teste bate numa porta que ainda não responde.

O resultado sai assim:

```
tests/integration/test_healthcheck.py::TestHealthCheck::test_home PASSED
...
============================== 35 passed in 1.54s ==============================
```

Para rodar só um arquivo (ou só um teste), acrescente o caminho:

```bash
pytest -v tests/integration/test_healthcheck.py
```

Os testes leem o seu `.env` sozinhos (é o `tests/conftest.py` que faz
isso). Trocou a porta da API ali, os testes passam a bater na porta nova
— você não configura a mesma coisa em dois lugares.

Os testes conversam com a API **por HTTP**, exatamente como um cliente de
verdade faria. Eles não espiam o código por dentro: nenhum deles importa
nada de `src/`. Só sabem: "mandei isso, tem que voltar aquilo".

> Uma exceção, e ela é honesta: `tests/utils/db_utils.py` fala com o
> banco direto, por SQLAlchemy. Mas não para **montar** cenário — só
> para **zerar** o banco entre testes que não podem se atrapalhar. O
> cenário continua nascendo pela API, com `POST`.

Isso tem uma consequência bonita: **este projeto inteiro já foi reescrito
de um framework para outro, e nenhum teste precisou mudar.** Quando o
teste descreve o combinado em vez de descrever o código, ele sobrevive à
reforma.

## 3. Quando dá errado

Os tropeços mais comuns, com a mensagem que você vai ver:

### `port is already allocated`

```
Bind for 0.0.0.0:5432 failed: port is already allocated
```

Outro programa da sua máquina já usa aquela porta (é comum ter um
Postgres instalado ocupando a 5432). Não precisa descobrir qual: escolha
outras portas livres. É pra isto que serve o `.env` —

```bash
cp .env.example .env
```

— e, dentro dele, tire o `#` da frente destas duas linhas e troque os
números:

```
API_PORT=3001
DB_PORT=5433
```

Mexeu no `DB_PORT`? Então mude **também** a porta da `DATABASE_URL`, no
mesmo arquivo:

```
DATABASE_URL=postgresql+psycopg2://bootcamp:bootcamp@localhost:5433/bootcamp
```

São dois lugares porque são dois pontos de vista. O `DB_PORT` diz em
que porta **da sua máquina** o banco aparece; a `DATABASE_URL` é o
endereço que os testes usam para chegar nele de fora do Docker. A API
lá dentro não usa nenhuma das duas — para ela o banco é `db:5432`, e
por isso essa linha está fixa no `docker-compose.yml`.

Suba de novo. Agora a API atende em http://localhost:3001 — e nos
comandos `curl` da seção 1 você troca `3000` por `3001`.

### `failed to connect to the docker API`

```
failed to connect to the docker API at unix:///var/run/docker.sock;
check if the path is correct and if the daemon is running
```

O Docker não está ligado. Abra o **Docker Desktop** (Mac/Windows) e
espere ficar verde. No Linux: `sudo systemctl start docker`.

### `Não consegui falar com a API` / `Não consegui falar com o banco`

Só aparece no atalho local (fora do Docker). Quer dizer que a API ou o
banco não estão de pé, ou que a porta no seu `.env` não é a que eles
estão usando. Suba com `docker compose up` e confira as portas.

### `relation "..." does not exist`

```
psycopg2.errors.UndefinedTable: relation "minha_tabela" does not exist
```

Você mexeu no `database/database.sql`, e o banco não ficou sabendo.
Aquele arquivo roda **uma vez só: quando o banco nasce.** Depois disso o
Postgres nunca mais olha para ele — subir de novo com `docker compose
up` não adianta, e `docker compose restart db` também não.

Repare no que a mensagem faz com você: ela não diz "seu SQL não rodou",
diz que a tabela não existe. Você vai reler o seu SQL procurando um erro
de digitação que não está lá.

Para o banco nascer de novo, já com o schema novo:

```bash
docker compose down -v
docker compose up
```

O `-v` é o que apaga o volume — o disco do banco. **Ele leva junto tudo
que você tinha criado na mão**, as entidades dos `curl` da seção 1. Não
tem meio-termo: ou o banco nasce de novo com o schema novo, ou continua
com o antigo. (Em sistema de verdade é outra história — lá ninguém apaga
o banco, e a mudança de schema entra por um comando aplicado no deploy.)

### Nada disso resolveu?

Este comando desliga e limpa **este** projeto (containers, rede e o
banco com tudo dentro) para você recomeçar do zero:

```bash
docker compose down -v
docker compose up
```

Para ver o que a API está dizendo enquanto roda: `docker compose logs -f api`.

---

## 4. As pastas

```
src/
  app.py           ← liga tudo: rotas, middlewares e tratamento de erro
  database.py      ← onde a sessão de banco mora (quem cuida do ciclo
                     dela é middlewares/session_manager.py)
  constants.py     ← as configurações, lidas do ambiente

  resources/       ← recebe a requisição HTTP e devolve a resposta
                     (quem liga cada endereço a um resource é o app.py)
  schemas/         ← o formato do que entra: o JSON do corpo e os
                     parâmetros do endereço
  controllers/     ← as regras de negócio: o que pode e o que não pode
  repositories/    ← as conversas com o banco
  models/          ← as tabelas, descritas em Python
  dtos/            ← traduz o objeto do banco no JSON que sai
  errors/          ← os erros da API, cada um com seu código
  middlewares/     ← o que acontece com TODA requisição
  connectors/      ← as conversas com outros serviços
  utils/           ← as ferramentas que não são de nenhuma camada

database/
  database.sql     ← as tabelas, em SQL puro

tests/             ← os testes
```

### Por que tanta pasta?

Porque cada uma tem **um trabalho só**, e só conversa com a vizinha:

```
requisição → resource → controller → repository → banco
                 ↑           ↑
             valida o     decide o
              formato     que pode
```

O resource não sabe SQL. O repository não sabe o que é uma regra de
negócio. Um teste rápido para saber se uma linha está na pasta certa:
**nenhum `raise` mora em `resources/`** — quem recusa é o schema, antes,
ou o controller, depois. Confira você mesmo:

```bash
grep -rn "raise" src/resources/
```

Não volta nada, e isso é de propósito. Quando você precisa trocar o banco, mexe numa pasta. Quando a
regra muda, mexe na outra. É isso que permite um time inteiro trabalhar
no mesmo projeto sem pisar no pé um do outro.

---

## 5. Configuração e senhas

Toda configuração entra por **variável de ambiente** — nunca escrita no
meio do código.

- **valor padrão** → escrito no `docker-compose.yml`, na forma
  `${VARIAVEL:-padrao}`. É por causa dele que o `docker compose up`
  funciona sem preparo nenhum.
- `.env` → **opcional**, fica só na sua máquina e **nunca** vai para o
  Git. Serve para sobrescrever um padrão (porta ocupada, outro token).
- `.env.example` → vai para o Git, e é a cópia de onde você parte. Só
  tem valor de mentirinha.

Essa separação não é frescura. Senha commitada em repositório é uma das
formas mais comuns de vazamento de dados no mundo real, e não tem
desfazer: uma vez no histórico, está lá para sempre.

Uma ressalva honesta: valor padrão de senha em arquivo versionado só
vale porque aqui é um projeto de estudo, sem dado de ninguém. Em
sistema de verdade, segredo não tem padrão — ele falta, e a aplicação
se recusa a subir sem ele.

## 6. Autenticação

As rotas de negócio pedem um cabeçalho:

```
INTERNAL-TOKEN: default_token
```

Sem ele, a API responde **403**. `default_token` é o valor padrão; para
trocar, ponha `INTERNAL_TOKEN=outra_coisa` no seu `.env`.

Ficam abertas, de propósito, só duas: a rota raiz e o `/health_check`
— esta última porque quem a consulta é o próprio Docker, que não tem
como mandar cabeçalho.

---

## 7. Os códigos de erro

Todo erro da API responde no mesmo formato, com um código próprio:

```json
{
  "title": "Bad Request",
  "description": "'hello' is a required property",
  "translation": "Payload Inválido",
  "code": "QIT000001"
}
```

| Código      | Quando acontece                                  |
|-------------|--------------------------------------------------|
| `QIT000001` | o JSON enviado está fora do formato              |
| `QIT000002` | faltou o `INTERNAL-TOKEN`, ou ele está errado    |
| `QIT000010` | os parâmetros do endereço se contradizem         |
| `QIT000404` | essa rota não existe                             |
| `QIT000405` | a rota existe, mas não aceita esse método        |
| `QIT000500` | erro inesperado (o time é avisado)               |
| `QIT001001` | a entidade procurada não existe                  |
| `QIT001002` | a entidade já está num status final              |
| `QIT001003` | o CPF tem o formato certo, mas não é um CPF      |
| `QIT001004` | já existe um cadastro com esse CPF               |
| `QIT001005` | já existe um cadastro com esse e-mail            |
| `QIT001006` | a pessoa é menor de idade                        |
| `QIT001007` | a data de nascimento não existe no calendário    |

Um código estável vale mais que uma mensagem bonita: quem integra com a
API programa em cima do código, não do texto.

Os números não são sorteados. Eles vêm em duas faixas:

- **`QIT000…`** — os erros que **toda** API tem: JSON errado, sem token,
  rota inexistente. Estão em `src/errors/base_error.py` e você não
  precisa mexer neles.
- **`QIT001…`** — os erros das **regras deste projeto**. Estão em
  `src/errors/custom_errors.py`, e é aí que os seus entram: o próximo
  livre é o `QIT001008`.

Não repita um número. Se repetir, a API **não sobe** — tem uma checagem
no start (`error_verification`, em `src/errors/base_error.py`) que
procura código repetido e derruba a aplicação de propósito. Parecer
chato agora é melhor que dois erros diferentes chegarem ao cliente com o
mesmo código.

---

## 8. A licença

Este projeto é **MIT** — pode usar, copiar, modificar e levar para o seu
portfólio, inclusive em trabalho pago. O único pedido é manter o arquivo
`LICENSE` junto quando você distribuir o código.

---

## 9. Acréscimos à base

Este repositório é o **Ledger**, uma cópia da base acima. A cópia só
recebeu linhas novas; nenhuma linha da base foi mudada. O que ela ganhou
além de rota, erro e tabela vem justificado aqui, em quatro linhas.

### Os mocks (`party-mock` e `provider-mock`, no `docker-compose.yml`)

1. *Princípio da base tocado:* o compose da base sobe só `api` e `db`.
2. *Por que não funciona sem:* os testes de integração falam HTTP com a
   API, e a API chama o Cadastro e o provedor Pix; sem mock, nenhum teste
   roda sem os três serviços de pé.
3. *A peça, e por que é a menor:* um container WireMock por dependência,
   configurado só por arquivos JSON — zero código.
4. *O que ela não faz:* não roda em produção, não guarda estado entre
   execuções, não substitui o teste ponta a ponta.

### O erro gravado pela chave de idempotência (`PostingController.post`, fatia 05a)

1. *Princípio da base tocado:* erro previsto não grava nada, e o controller
   só commita depois que a regra passou.
2. *Por que não funciona sem:* a mesma `Idempotency-Key` tem de devolver o
   mesmo erro. Sem o erro gravado, a repetição — ou a requisição que
   esperava no `INSERT` da mesma chave — roda o motor de novo e pode
   responder outra coisa.
3. *A peça, e por que é a menor:* um `SAVEPOINT` logo depois do registro da
   chave. No erro, `ROLLBACK TO SAVEPOINT` desfaz só o movimento; o registro
   recebe o status e o código; e o commit é o da mesma transação, sem
   sessão nova nem segundo commit.
4. *O que ela não faz:* não grava falha de schema, o `QIT001035`, o
   `QIT001019` (S05b D-01) nem o `QIT001018` da conta de origem ou de
   destino de `/transfers/payout` e `/transfers/internal` e da conta de
   `/statement`, nem o `QIT001020` do estorno (transação inexistente) e do
   MED (`end_to_end_id` desconhecido) (que saem antes do registro; S09 D-01,
   S15a D-01, S13 RN-04, S11 D-01),
   não grava erro do webhook do provedor (que é idempotente pelo
   `provider_event` e desfaz tudo no erro, para o provedor repetir),
   não grava movimento pela metade, não tenta de novo e não guarda a
   `description` dinâmica do erro.

### O `QIT001010` também cobre o `end_to_end_id` repetido (fatia 05a)

O guia e a RFC definem o `QIT001010` como "mesma chave, corpo diferente". Na
entrada por Pix, o `end_to_end_id` é a chave natural do pagamento: o mesmo
Pix chegando sob outra `Idempotency-Key` também responde `409 QIT001010`,
e esse erro fica gravado sob a chave nova. Não é peça nova: é o mesmo
código, com o significado estendido.

### A lista de negativos suspeitos do `GET /integrity` só se prova vazia (fatia 06)

O `GET /integrity` devolve, além dos totais, as contas com saldo negativo
e nenhum lançamento em transação `reversal` (D0005): um negativo sem
estorno no histórico só nasce de bug ou de SQL feito à mão (CU-H3). Nenhuma
rota leva uma conta a esse estado, então nenhum teste por HTTP prova a
lista cheia: a suíte prova só que ela sai vazia. O negativo **com** estorno,
que não entra na lista, é o caso que a fatia 11 prova (CU-H2). Não é peça
nova: é um limite declarado.

### A trava de uma linha nos testes (`DbUtils.hold_row_lock`, fatia 08)

1. *Princípio da base tocado:* o `db_utils` dos testes só zera o banco;
   nunca monta cenário.
2. *Por que não funciona sem:* a ordem "entrada passa a conferência de
   status → encerramento commita → entrada grava" não se produz por HTTP;
   threads simultâneas só a sorteiam, e sem ela a reconferência de status
   do encerramento não tem teste que falhe.
3. *A peça, e por que é a menor:* trava **uma** linha de `ledger_account`,
   em conexão própria, pelo tempo de um `with`; não muda nada, e o
   `ROLLBACK` a solta.
4. *O que ela não faz:* não escreve (`INSERT`, `UPDATE`, `DELETE`), não
   executa SQL livre, não lê dado para asserção, não monta cenário — o
   cenário nasce por `POST`.

A mesma peça prova o `409 QIT001011` da divisão (fatia 07): o teste segura a
`COLLECTION` com `hold_row_lock` além do `lock_timeout` (S07 D-01).

### Os connectors do Cadastro e do provedor (`PartyConnector`, `ProviderConnector`, fatia 09)

1. *Princípio da base tocado:* a base só tem o `bankslip_connector`, fora
   de qualquer fluxo.
2. *Por que não funciona sem:* o Ledger não guarda chave Pix — ela vem do
   Cadastro a cada repasse — e o Pix só sai pelo provedor.
3. *A peça, e por que é a menor:* duas subclasses de `RestConnector`, um
   método cada, com timeout vindo do ambiente: o padrão que a base já
   ensina.
4. *O que ela não faz:* transforma só a falha de rede em `None`; não
   interpreta status, não tenta de novo, não guarda chave, não abre
   transação.

### A outbox com despacho inline (`POST /transfers/payout` por Pix, fatia 09)

1. *Princípio da base tocado:* a base faz um commit, na última linha do
   controller.
2. *Por que não funciona sem:* chamar o provedor dentro da transação
   prende a trava da conta durante a chamada de rede; commitar e chamar
   sem outbox perde o repasse se o processo cair entre os dois; e ler o
   dono da conta no banco antes de chamar o Cadastro já abre uma
   transação.
3. *A peça, e por que é a menor:* a outbox gravada no mesmo commit das
   pernas, mais dois commits de estado (`in_flight`, resultado) e o commit
   que fecha a leitura: quatro commits numa requisição, sem fila nem
   agendador.
4. *O que ela não faz:* não reenvia nem marca `dead` (isso é da fila,
   abaixo), não tem backoff, não liquida, e não segura trava durante a
   chamada externa. Com a fila, o despacho reivindica a linha antes de
   enviar e pode voltar sem despachar, se outro já a reivindicou.

### A trava da transação original nos testes (`DbUtils.hold_transaction_lock`, fatia 11)

1. *Princípio da base tocado:* o `db_utils` dos testes só zera o banco;
   nunca monta cenário.
2. *Por que não funciona sem:* a trava da transação original só decide a
   corrida entre estornos quando nenhuma conta os ordena antes; por HTTP, a
   `COLLECTION` já os ordena, e só o estorno sem conta travável (uma
   liquidação) a exporia, e apenas por sorteio — sem a peça, essa regra não
   tem teste que falhe de forma determinística.
3. *A peça, e por que é a menor:* trava **uma** linha de
   `ledger_transaction`, em conexão própria, pelo tempo de um `with`; o
   `ROLLBACK` a solta.
4. *O que ela não faz:* não escreve, não executa SQL livre, não lê dado
   para asserção, não monta cenário — o cenário nasce por `POST`.

### O estorno parcial só vale com pernas de valor igual (fatia 11, D4)

A RFC (`:151`) aceita `amount_in_cents` no `POST /transfers/{key}/reversal`
sem restringir o parcial. O Ledger o aceita só quando todas as pernas da
original têm o mesmo valor (Pix, repasse, liquidação, carteira): cada perna
do estorno recebe o valor pedido. Na divisão, de pernas desiguais, o
parcial responde `400 QIT000001` e nada se grava: ratear foi descartado no
pagamento parcial (RFC `:376-378`, por analogia), e corrigir uma divisão é
estorná-la inteira e alocar de novo (D0005). O `400` é um compromisso: o
correto seria um `422`, mas nenhum código do guia cabe, e nenhuma fatia
inventa código. Não é peça nova: é um limite declarado.

### A fila de redespacho (`POST /outbox/dispatch`, fatia 14)

1. *Princípio da base tocado:* a base faz um commit, na última linha do
   controller.
2. *Por que não funciona sem:* o repasse que ficou `pending` por queda ou
   falha do provedor nunca sairia.
3. *A peça, e por que é a menor:* uma tentativa por linha, com dois
   commits (`in_flight`, resultado), reivindicando a linha com `SKIP
   LOCKED` — a linha travada por outro é pulada — e marcando `dead` ao
   esgotar o `OUTBOX_MAX_ATTEMPTS`; disparada por rota, sem agendador.
4. *O que ela não faz:* não tem backoff nem relógio, não estorna o `dead`
   (o operador estorna pela rota de estorno), não tira linha de
   `in_flight` e não segura trava durante a chamada externa.

### A trava de uma linha da outbox nos testes (`DbUtils.hold_outbox_lock`, fatia 14)

1. *Princípio da base tocado:* o `db_utils` dos testes só zera o banco.
2. *Por que não funciona sem:* duas reivindicações simultâneas da mesma
   linha não se produzem por HTTP de forma determinística; sem a peça, o
   `SKIP LOCKED` não tem teste que falhe.
3. *A peça, e por que é a menor:* trava uma linha de `outbox`, em conexão
   própria, pelo tempo de um `with`; o `ROLLBACK` a solta.
4. *O que ela não faz:* não escreve, não executa SQL livre, não lê dado
   para asserção, não monta cenário.

### O aceite temporário no mock do provedor (`RequestGenerator.accept_pix`, fatia 14)

1. *Princípio da base tocado:* o mock responde fixo por chave Pix.
2. *Por que não funciona sem:* nenhum mock falha e depois aceita, e o
   despacho tardio pela fila precisa ser provado.
3. *A peça, e por que é a menor:* um mapeamento, para uma única chave de
   despacho do teste, criado pela API de administração do mock e apagado
   ao fim do teste.
4. *O que ela não faz:* não altera arquivo de mock, não persiste e não
   afeta outra chave.

### A trava `E2E=1` do ponto de integração (`tests/e2e/conftest.py`)

1. *Princípio da base tocado:* a suíte da base roda inteira com um
   `pytest`, sem variável nenhuma.
2. *Por que não funciona sem:* os testes de `tests/e2e/` falam com o
   Cadastro de verdade, que o `pytest` comum não tem de pé; sem a trava, a
   suíte contra os mocks falharia por um motivo que não é dela.
3. *A peça, e por que é a menor:* um `pytest_collection_modifyitems` que
   marca como `skip` tudo em `tests/e2e/` quando `E2E` não vale `1`.
4. *O que ela não faz:* não pula nada fora de `tests/e2e/`, não sobe o
   Cadastro e não troca o `PARTY_API_URL` da API.

### O marcador `destrutivo` (`tests/e2e/conftest.py`)

1. *Princípio da base tocado:* todo teste da base pode rodar junto de
   qualquer outro.
2. *Por que não funciona sem:* o caso "Cadastro fora do ar" para o
   container do Cadastro; rodando junto de outro teste, derruba esse outro.
3. *A peça, e por que é a menor:* um marcador registrado no
   `pytest_configure`; o teste marcado só roda com `E2E_DESTRUTIVO=1` a
   mais, e sozinho.
4. *O que ela não faz:* não isola nada por conta própria: quem garante que
   nada mais depende do Cadastro naquele momento é quem roda.

### As partes reais do ponto de integração (`tests/utils/party_scenarios.py`)

1. *Princípio da base tocado:* o cenário nasce por `POST` na própria API, e
   as chaves das partes são as mágicas do `party-mock`.
2. *Por que não funciona sem:* as chaves mágicas (`2222…`, `aaaa…`, `dddd…`,
   `eeee…`, `ffff…`) não existem no Cadastro de verdade.
3. *A peça, e por que é a menor:* `seed_party_scenarios()` cria cada papel
   por `POST /parties` no Cadastro real e devolve `{papel: party_key}`; a
   fixture `party_scenarios` semeia uma vez por `pytest`.
4. *O que ela não faz:* não roda contra o `party-mock` (recusa, se o
   `PARTY_API_URL` apontar para ele), não apaga as partes que cria e não
   muda os testes contra os mocks.

### O Cadastro fora do ar de verdade (`tests/e2e/test_party_api_down.py`)

1. *Princípio da base tocado:* teste fala HTTP com a API e não mexe em
   container.
2. *Por que não funciona sem:* o `cccc…` do `party-mock` simula o Cadastro
   fora do ar com um atraso; contra o Cadastro real, a única forma de
   prová-lo é o serviço estar fora do ar.
3. *A peça, e por que é a menor:* um teste que dá `docker compose stop` no
   container `api` do Cadastro (a pasta vem de `PARTY_COMPOSE_DIR`), exige
   `503 QIT001040` sem conta gravada e o sobe de volta no `finally`.
4. *O que ela não faz:* não roda sem `E2E=1` e `E2E_DESTRUTIVO=1`, não
   para o banco do Cadastro e não termina antes de o `/health_check` dele
   responder de novo.


## 10. Como subir o Ledger

Aqui o `.env` **não é opcional**: é nele que estão as portas do Ledger e
os valores com que a suíte roda. Sem ele, a API sobe nas portas da base.

```bash
cp .env.example .env
docker compose up -d --wait
git config core.hooksPath .githooks
```

A terceira linha liga o `.githooks/commit-msg`, que confere a mensagem de
cada commit. Ela vale para o seu clone e só precisa rodar uma vez.

São quatro coisas de pé, cada uma numa porta da sua máquina:

| Serviço | Porta | O que é |
|---|---|---|
| `api` | `3003` | a API do Ledger (http://localhost:3003) |
| `db` | `5435` | o banco do Ledger |
| `party-mock` | `8091` | o mock do Cadastro |
| `provider-mock` | `8082` | o mock do provedor de pagamentos |

Os testes rodam como na seção 2, com `pytest`, e batem na `3003`.

### No ponto de integração, contra o Cadastro de verdade

Quem responde pelo Cadastro é o serviço real, então o `party-mock` não
sobe. No seu `.env`, troque o endereço do Cadastro:

```
PARTY_API_URL=http://host.docker.internal:3001
```

e suba sem o mock:

```bash
docker compose up -d api db provider-mock
```

Contra o Cadastro real, use `PARTY_API_TIMEOUT=3` no `.env`: o `1` do
`.env.example` é o valor da suíte, feito para os mocks de "fora do ar".

Os testes do ponto de integração ficam em `tests/e2e/` e só rodam com
`E2E=1` (sem ela, aparecem como `skipped`):

```bash
E2E=1 PARTY_API_URL=http://host.docker.internal:3001 API_PORT=3003   SERVER_LOCALHOST=localhost pytest tests/e2e
```

O `test_party_api_down.py` para o Cadastro de verdade: ele pede
`E2E_DESTRUTIVO=1` a mais e roda sozinho, nunca junto de outro teste que
dependa do Cadastro de pé (seção 9).

Precisa dos dois mocks de pé ao mesmo tempo e a `8091` está ocupada?
Troque o `PARTY_MOCK_PORT` no `.env`.

## 11. As rotas do Ledger, uma a uma

Toda rota do Ledger, com o verbo e o caminho como estão no `src/app.py`:

| Verbo | Caminho | O que faz |
|---|---|---|
| `GET` | `/ledger_accounts/{ledger_account_key}` | lê uma conta e o saldo dela |
| `POST` | `/contract_ledgers` | provisiona o livro do contrato (as contas do split) |
| `POST` | `/contract_ledgers/{contract_key}/closure` | encerra as contas do contrato |
| `GET` | `/ledger_accounts` | lista as contas de um cliente, contrato ou dono |
| `PUT` | `/ledger_accounts/{ledger_account_key}/status` | bloqueia, desbloqueia ou encerra uma conta |
| `POST` | `/transfers/inflow` | entrada por Pix: no contrato ou depósito na carteira |
| `GET` | `/transfers/{ledger_transaction_key}/trace` | rastreia a transação e a cadeia do contrato |
| `POST` | `/transfers/split` | divide a competência do contrato |
| `POST` | `/transfers/payout` | repassa ao dono da conta, por Pix ou para a carteira |
| `POST` | `/transfers/internal` | move entre contas do mesmo livro |
| `POST` | `/transfers/{ledger_transaction_key}/reversal` | estorna uma transação |
| `GET` | `/transfers` | lista as transações de um pagador, ou de um contrato na competência |
| `GET` | `/integrity` | confere que o livro fecha em zero |
| `POST` | `/statement` | emite o extrato do período, com hash encadeado |
| `POST` | `/statement/verify` | diz se um hash de extrato bate (pública) |
| `GET` | `/statement/{statement_key}` | lê um extrato |
| `POST` | `/webhooks/provider` | o aviso do provedor: liquidação ou MED |
| `POST` | `/wallets` | abre a carteira de uma parte |
| `POST` | `/outbox/dispatch` | despacha os repasses que ficaram `pending` |

Os exemplos seguem o caso do `remodelagem/05`, no contrato
`0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c` da Imobiliária Alfa, e rodam no Git
Bash, na ordem, com a pilha da seção 10 de pé. Toda rota pede o
`INTERNAL-TOKEN`, menos o `/statement/verify`. Um valor que só o servidor
conhece aparece como `$NOME`: copie-o da resposta indicada e defina a
variável antes de rodar o bloco (`RENT_KEY=...`).

As partes dos exemplos (`1111…`, `2222…`, `3333…`, `4444…` a `7777…`) são
chaves do `party-mock`, a pilha da seção 10 com os mocks. Contra o Cadastro
de verdade elas não existem, e as rotas que consultam o dono respondem
`409`: crie antes cada parte por `POST /parties` no Cadastro e troque a
chave pela `party_key` da resposta.

O provisionamento (`01b` §3). Da resposta, em `accounts`, saem o
`ledger_account_key` da `RENT` (`$RENT_KEY`), o da `OWN` (`$OWN_KEY`) e o
da `COLLECTION` (`$COLLECTION_KEY`).

```bash
curl -X POST http://localhost:3003/contract_ledgers \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{"contract_key": "0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c", "client_key": "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1", "client_party_key": "11111111-1111-4111-8111-111111111111", "split_version": 1, "rent_amount_in_cents": 500000, "platform_fee_percentage": "1.0000", "items": [{"purpose_code": "RENT", "beneficiary_party_key": "22222222-2222-4222-8222-222222222222", "beneficiary_role": "landlord", "type": "remainder"}, {"purpose_code": "OWN", "beneficiary_party_key": "11111111-1111-4111-8111-111111111111", "beneficiary_role": "administrator", "type": "percentage", "value": "10.0000"}, {"purpose_code": "IPTU", "beneficiary_party_key": "44444444-4444-4444-8444-444444444444", "beneficiary_role": "provider", "type": "fixed", "value": 30000}, {"purpose_code": "CONDO", "beneficiary_party_key": "55555555-5555-4555-8555-555555555555", "beneficiary_role": "provider", "type": "fixed", "value": 80000}, {"purpose_code": "WATER", "beneficiary_party_key": "66666666-6666-4666-8666-666666666666", "beneficiary_role": "provider", "type": "fixed", "value": 12000}, {"purpose_code": "ELECTRICITY", "beneficiary_party_key": "77777777-7777-4777-8777-777777777777", "beneficiary_role": "provider", "type": "fixed", "value": 18000}], "actor": "contract-api", "reason": "ativacao do contrato ALFA-2026-0042"}'
```

As contas do contrato, e uma delas pela chave:

```bash
curl -X GET "http://localhost:3003/ledger_accounts?contract_key=0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c" \
  -H "INTERNAL-TOKEN: default_token"
```

```bash
curl -X GET http://localhost:3003/ledger_accounts/$RENT_KEY \
  -H "INTERNAL-TOKEN: default_token"
```

A TX1, o Pix do Bruno, com a `Idempotency-Key` igual ao `end_to_end_id`.
Da resposta sai o `ledger_transaction_key` (`$INFLOW_KEY`).

```bash
curl -X POST http://localhost:3003/transfers/inflow \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Idempotency-Key: E00000000202609051422abc" \
  -H "Content-Type: application/json" \
  -d '{"amount_in_cents": 640000, "contract_key": "0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c", "period_reference": "2026-09", "payer_party_key": "33333333-3333-4333-8333-333333333333", "end_to_end_id": "E00000000202609051422abc", "value_date": "2026-09-05T14:22:00Z", "actor": "erp-alfa"}'
```

A TX2, a divisão da competência:

```bash
curl -X POST http://localhost:3003/transfers/split \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Idempotency-Key: split-0c0c-2026-09" \
  -H "Content-Type: application/json" \
  -d '{"contract_key": "0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c", "period_reference": "2026-09", "value_date": "2026-09-05T14:23:00Z", "actor": "erp-alfa"}'
```

O rastreio da TX1, com a cadeia do contrato na competência:

```bash
curl -X GET http://localhost:3003/transfers/$INFLOW_KEY/trace \
  -H "INTERNAL-TOKEN: default_token"
```

As transações do contrato na competência:

```bash
curl -X GET "http://localhost:3003/transfers?contract_key=0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c&period_reference=2026-09" \
  -H "INTERNAL-TOKEN: default_token"
```

A TX3, o repasse dos 450000 da `RENT` à Ana. Da resposta, em `outbox`, saem
o `outbox_key` (`$OUTBOX_KEY`) e a `dispatch_idempotency_key`
(`$DISPATCH_KEY`).

```bash
curl -X POST http://localhost:3003/transfers/payout \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Idempotency-Key: repasse-0c0c-rent-2026-09" \
  -H "Content-Type: application/json" \
  -d '{"source_account_key": "'"$RENT_KEY"'", "amount_in_cents": 450000, "destination": "pix", "period_reference": "2026-09", "actor": "erp-alfa", "reason": "repasse aluguel 09/2026"}'
```

A TX4, o provedor confirma a liquidação do repasse:

```bash
curl -X POST http://localhost:3003/webhooks/provider \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{"provider_reference": "PRV-'"$DISPATCH_KEY"'-SETTLED", "event_type": "settlement_confirmed", "outbox_key": "'"$OUTBOX_KEY"'", "value_date": "2026-09-06T10:00:00Z"}'
```

A fila da outbox: despacha o repasse que ficou `pending` (o provedor fora
do ar na TX3, por exemplo), até `limit` linhas por chamada:

```bash
curl -X POST http://localhost:3003/outbox/dispatch \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}'
```

O estorno da TX1, pelo ERP:

```bash
curl -X POST http://localhost:3003/transfers/$INFLOW_KEY/reversal \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Idempotency-Key: estorno-0c0c-tx1" \
  -H "Content-Type: application/json" \
  -d '{"actor": "erp-alfa", "reason": "estorno do aluguel 09/2026"}'
```

A TX8, a Alfa devolve a própria taxa ao contrato:

```bash
curl -X POST http://localhost:3003/transfers/internal \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Idempotency-Key: devolucao-taxa-0c0c-2026-09" \
  -H "Content-Type: application/json" \
  -d '{"source_account_key": "'"$OWN_KEY"'", "gross_amount_in_cents": 45000, "allocations": [{"target_account_key": "'"$COLLECTION_KEY"'", "type": "remainder"}], "actor": "gerente-financeiro@alfa", "reason": "devolucao de taxa - MED 09/2026"}'
```

A integridade do livro da Alfa:

```bash
curl -X GET "http://localhost:3003/integrity?client_key=c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1" \
  -H "INTERNAL-TOKEN: default_token"
```

O extrato de setembro da `RENT`. Da resposta saem o `statement_key`
(`$STATEMENT_KEY`) e o `content_hash` (`$CONTENT_HASH`).

```bash
curl -X POST http://localhost:3003/statement \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Idempotency-Key: extrato-0c0c-rent-2026-09" \
  -H "Content-Type: application/json" \
  -d '{"ledger_account_key": "'"$RENT_KEY"'", "period_start": "2026-09-01T00:00:00Z", "period_end": "2026-10-01T00:00:00Z", "actor": "erp-alfa"}'
```

```bash
curl -X GET http://localhost:3003/statement/$STATEMENT_KEY \
  -H "INTERNAL-TOKEN: default_token"
```

A verificação do hash, pública, sem o `INTERNAL-TOKEN`:

```bash
curl -X POST http://localhost:3003/statement/verify \
  -H "Content-Type: application/json" \
  -d '{"content_hash": "'"$CONTENT_HASH"'"}'
```

A carteira da Ana:

```bash
curl -X POST http://localhost:3003/wallets \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{"party_key": "22222222-2222-4222-8222-222222222222", "actor": "erp-alfa"}'
```

O bloqueio de uma conta. Da resposta do provisionamento, em `accounts`, sai
o `ledger_account_key` do `IPTU` (`$IPTU_KEY`):

```bash
curl -X PUT http://localhost:3003/ledger_accounts/$IPTU_KEY/status \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{"status": "blocked", "actor": "erp-alfa", "reason": "conferencia do IPTU 09/2026"}'
```

O encerramento do contrato (`01b` §4). Com saldo retido em alguma conta, a
resposta é `409 QIT001037`.

```bash
curl -X POST http://localhost:3003/contract_ledgers/0c0c0c0c-0c0c-40c0-80c0-0c0c0c0c0c0c/closure \
  -H "INTERNAL-TOKEN: default_token" \
  -H "Content-Type: application/json" \
  -d '{"actor": "contract-api", "reason": "fim da locacao ALFA-2026-0042"}'
```

## 12. Códigos do Ledger

A seção 7 é a da base e continua igual. Os códigos das regras do Ledger
começam no `QIT001008`, estão em `src/errors/custom_errors.py` e são os do
guia do Ledger §7, sem tirar nem pôr:

| Código | Situação | HTTP |
|---|---|---|
| `QIT001008` | par de propósitos proibido / contratos diferentes | 422 |
| `QIT001009` | saldo insuficiente | 422 |
| `QIT001010` | mesma chave de idempotência, corpo diferente; ou `end_to_end_id` já usado sob outra chave (S05a D-01) | 409 |
| `QIT001011` | contenção além do `lock_timeout` | 409 |
| `QIT001012` | conta não aceita **movimento** no estado atual (não é transição de estado) | 409 |
| `QIT001013` | atravessaria livros de clientes (rota `internal`) | 422 |
| `QIT001014` | moedas divergentes | 422 |
| `QIT001015` | estornos excederiam o original | 422 |
| `QIT001016` | não se estorna estorno | 422 |
| `QIT001017` | período já tem extrato | 409 |
| `QIT001018` | conta inexistente | 404 |
| `QIT001019` | cliente sem livros no ledger | 404 |
| `QIT001020` | transação inexistente | 404 |
| `QIT001022` | extrato inexistente | 404 |
| `QIT001028` | propósito inexistente | 422 |
| `QIT001031` | outbox inexistente | 404 |
| `QIT001032` | versão de split já provisionada com outro conteúdo | 409 |
| `QIT001033` | versão de split fora de sequência | 409 |
| `QIT001034` | split não fecha: percentuais ≥ 100%, ou taxa da plataforma > taxa de administração | 422 |
| `QIT001035` | contrato não provisionado | 404 |
| `QIT001036` | competência já dividida | 409 |
| `QIT001037` | conta com saldo não pode ser encerrada | 409 |
| `QIT001038` | dono não está ativo no cadastro | 409 |
| `QIT001039` | dono sem chave Pix | 422 |
| `QIT001040` | cadastro indisponível | 503 |
| `QIT001041` | dono sem carteira | 404 |
| `QIT001042` | a transação não fecha em zero em algum livro | 500 |
| `QIT001043` | transição de estado da conta inválida | 409 |

`QIT001021`, `023`–`027`, `029`, `030` estão **aposentados**: não use.

Os números estão fixados (sumário das specs §4): o "próximo livre" da
seção 7 não vale aqui, e um código aposentado não volta.
