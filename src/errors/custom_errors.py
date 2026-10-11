from errors import QIException


class NotFoundSampleEntity(QIException):
    code = "QIT001001"

    def __init__(self, sample_entity_key) -> None:
        title = "Entity not Found"
        http_status = 404
        description = f"Entity with key {sample_entity_key} was not found."
        translation = f"A entidade com chave {sample_entity_key} não foi encontrada."
        super().__init__(title, self.code, http_status, description, translation)


class SampleEntityFinalStatus(QIException):
    code = "QIT001002"

    def __init__(self, old_status, new_status) -> None:
        title = "Entity cannot change status"
        http_status = 409
        description = f"Entity with status {old_status} cannot update to {new_status}."
        translation = "Essa entidade não pode ser atualizada."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidDocumentNumber(QIException):
    """O CPF tem o formato certo e não existe.

    422, e não 400, de propósito: 400 quer dizer "não consegui ler o seu
    pedido". Aqui a API leu, entendeu, e o valor é que não pode existir —
    os dois últimos dígitos não batem com a conta. A diferença está
    explicada em src/utils/document_number.py.
    """

    code = "QIT001003"

    def __init__(self, document_number) -> None:
        title = "Invalid Document Number"
        http_status = 422
        description = f"The document number {document_number} is not a valid CPF."
        translation = "O CPF informado não é válido."
        super().__init__(title, self.code, http_status, description, translation)


class DuplicatedDocumentNumber(QIException):
    """Já existe um cadastro com este CPF.

    409 Conflict: o pedido está correto em si, e o que impede é o que já
    está no banco. É a mesma família do SampleEntityFinalStatus aqui em
    cima — conflito com o que já existe, não erro de quem pediu.
    """

    code = "QIT001004"

    def __init__(self, document_number) -> None:
        title = "Document Number already registered"
        http_status = 409
        description = f"There is already an entity with the document number {document_number}."
        translation = "Já existe um cadastro com este CPF."
        super().__init__(title, self.code, http_status, description, translation)


class DuplicatedEmail(QIException):
    code = "QIT001005"

    def __init__(self, email) -> None:
        title = "Email already registered"
        http_status = 409
        description = f"There is already an entity with the email {email}."
        translation = "Já existe um cadastro com este e-mail."
        super().__init__(title, self.code, http_status, description, translation)


class UnderageSampleEntity(QIException):
    code = "QIT001006"

    def __init__(self, age, minimum_age) -> None:
        title = "Entity is underage"
        http_status = 422
        description = f"The entity is {age} years old, and the minimum is {minimum_age}."
        translation = f"É preciso ter pelo menos {minimum_age} anos."
        super().__init__(title, self.code, http_status, description, translation)


class InvalidBirthdate(QIException):
    """A data tem o formato certo e não existe no calendário.

    Existe porque o `pattern` do schema sabe contar dígitos, não dias:
    "2025-02-30" e "9999-99-99" passam pelo regex e morrem no
    `date.fromisoformat`. Sem esta classe, esse ValueError virava 500 —
    a API culpando a si mesma por um erro de quem chamou.
    """

    code = "QIT001007"

    def __init__(self, birthdate) -> None:
        title = "Invalid Birthdate"
        http_status = 422
        description = f"The birthdate {birthdate} is not a real date."
        translation = "A data de nascimento informada não existe."
        super().__init__(title, self.code, http_status, description, translation)


class LedgerAccountNotFound(QIException):
    code = "QIT001018"

    def __init__(self, ledger_account_key=None) -> None:
        title = "Ledger Account not Found"
        http_status = 404
        description = "The ledger account was not found."
        if ledger_account_key is not None:
            description = f"Ledger account with key {ledger_account_key} was not found."
        translation = "conta inexistente"
        super().__init__(title, self.code, http_status, description, translation)


class SplitVersionConflict(QIException):
    code = "QIT001032"

    def __init__(self, contract_key, split_version) -> None:
        title = "Split version conflict"
        http_status = 409
        description = f"Split version {split_version} of contract {contract_key} already provisioned with different content."
        translation = "versão de split já provisionada com outro conteúdo"
        super().__init__(title, self.code, http_status, description, translation)


class SplitVersionOutOfSequence(QIException):
    code = "QIT001033"

    def __init__(self, contract_key, split_version, latest_split_version) -> None:
        title = "Split version out of sequence"
        http_status = 409
        description = (
            f"Split version {split_version} of contract {contract_key} is out of sequence: "
            f"the latest provisioned version is {latest_split_version}."
        )
        translation = "versão de split fora de sequência"
        super().__init__(title, self.code, http_status, description, translation)


class PurposePairNotAllowed(QIException):
    code = "QIT001008"

    def __init__(self, source_purpose_code=None, target_purpose_code=None) -> None:
        title = "Purpose pair not allowed"
        http_status = 422
        description = "The purpose pair is not in purpose_rule, or crosses contracts."
        if source_purpose_code is not None:
            description = f"Purpose pair {source_purpose_code} -> {target_purpose_code} is not in purpose_rule."
        translation = "par de propósitos proibido / contratos diferentes"
        super().__init__(title, self.code, http_status, description, translation)


class UnknownPurposeCode(QIException):
    code = "QIT001028"

    def __init__(self, purpose_code) -> None:
        title = "Unknown purpose code"
        http_status = 422
        description = f"The purpose code {purpose_code} does not exist."
        translation = "propósito inexistente"
        super().__init__(title, self.code, http_status, description, translation)


class SplitDoesNotClose(QIException):
    code = "QIT001034"

    def __init__(self, reason) -> None:
        title = "Split does not close"
        http_status = 422
        description = f"The split does not close: {reason}."
        translation = "split não fecha: percentuais ≥ 100%, ou taxa da plataforma > taxa de administração"
        super().__init__(title, self.code, http_status, description, translation)


class ContractNotProvisioned(QIException):
    code = "QIT001035"

    def __init__(self, contract_key=None) -> None:
        title = "Contract not provisioned"
        http_status = 404
        description = "The contract is not provisioned in the ledger."
        if contract_key is not None:
            description = f"The contract {contract_key} is not provisioned in the ledger."
        translation = "contrato não provisionado"
        super().__init__(title, self.code, http_status, description, translation)


class InsufficientBalance(QIException):
    code = "QIT001009"

    def __init__(self) -> None:
        title = "Insufficient balance"
        http_status = 422
        description = "The ledger account balance does not cover the debit."
        translation = "saldo insuficiente"
        super().__init__(title, self.code, http_status, description, translation)


class LockTimeout(QIException):
    code = "QIT001011"

    def __init__(self) -> None:
        title = "Lock timeout"
        http_status = 409
        description = "The ledger accounts stayed locked by another posting beyond the lock timeout."
        translation = "contenção além do lock_timeout"
        super().__init__(title, self.code, http_status, description, translation)


class LedgerAccountNotMovable(QIException):
    code = "QIT001012"

    def __init__(self) -> None:
        title = "Ledger account not movable"
        http_status = 409
        description = "A ledger account of the posting does not accept movement in its current status."
        translation = "conta não aceita movimento no estado atual"
        super().__init__(title, self.code, http_status, description, translation)


class CurrencyMismatch(QIException):
    code = "QIT001014"

    def __init__(self) -> None:
        title = "Currency mismatch"
        http_status = 422
        description = "The ledger accounts of the posting have different currencies."
        translation = "moedas divergentes"
        super().__init__(title, self.code, http_status, description, translation)


class TransactionDoesNotBalance(QIException):
    code = "QIT001042"

    def __init__(self) -> None:
        title = "Transaction does not balance"
        http_status = 500
        description = "The debits and credits of the transaction do not add up to zero in some book."
        translation = "a transação não fecha em zero em algum livro"
        super().__init__(title, self.code, http_status, description, translation)


class IdempotencyKeyConflict(QIException):
    code = "QIT001010"

    def __init__(self) -> None:
        title = "Idempotency key conflict"
        http_status = 409
        description = (
            "The Idempotency-Key was already used with a different request body, "
            "or the end_to_end_id was already used under another Idempotency-Key."
        )
        translation = "mesma chave de idempotência, corpo diferente; ou end_to_end_id já usado sob outra chave"
        super().__init__(title, self.code, http_status, description, translation)


class LedgerTransactionNotFound(QIException):
    code = "QIT001020"

    def __init__(self, ledger_transaction_key=None) -> None:
        title = "Ledger transaction not found"
        http_status = 404
        description = "The ledger transaction was not found."
        if ledger_transaction_key is not None:
            description = f"Ledger transaction with key {ledger_transaction_key} was not found."
        translation = "transação inexistente"
        super().__init__(title, self.code, http_status, description, translation)


class LedgerAccountHasBalance(QIException):
    code = "QIT001037"

    def __init__(self) -> None:
        title = "Account has balance"
        http_status = 409
        description = "An account of this contract has non-zero balance."
        translation = "conta com saldo não pode ser encerrada"
        super().__init__(title, self.code, http_status, description, translation)


class PeriodAlreadySplit(QIException):
    code = "QIT001036"

    def __init__(self) -> None:
        title = "Period already split"
        http_status = 409
        description = "The contract period was already split."
        translation = "competência já dividida"
        super().__init__(title, self.code, http_status, description, translation)


class StatementNotFound(QIException):
    code = "QIT001022"

    def __init__(self, statement_key=None) -> None:
        title = "Statement not found"
        http_status = 404
        description = "The statement was not found."
        if statement_key is not None:
            description = f"Statement with key {statement_key} was not found."
        translation = "extrato inexistente"
        super().__init__(title, self.code, http_status, description, translation)


class StatementPeriodAlreadyIssued(QIException):
    code = "QIT001017"

    def __init__(self, ledger_account_key=None, period_start=None, period_end=None) -> None:
        title = "Statement period already issued"
        http_status = 409
        description = "The period already has a statement, or overlaps another one."
        if ledger_account_key is not None:
            description = (
                f"Ledger account {ledger_account_key} already has a statement for "
                f"{period_start} - {period_end}, or one that overlaps it."
            )
        translation = "período já tem extrato"
        super().__init__(title, self.code, http_status, description, translation)
