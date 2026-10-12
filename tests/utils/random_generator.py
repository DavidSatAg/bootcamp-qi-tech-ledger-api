import random


class RandomGenerator:
    @staticmethod
    def generate_cpf():
        cpf = [random.randrange(10) for _ in range(9)]
        for _ in range(2):
            value = sum([(len(cpf) + 1 - i) * v for i, v in enumerate(cpf)]) % 11
            cpf.append(11 - value if value > 1 else 0)
        cpf_number = "".join(str(x) for x in cpf)
        cpf_number = f"{cpf_number[0:3]}.{cpf_number[3:6]}.{cpf_number[6:9]}-{cpf_number[9:11]}"
        return cpf_number

    @staticmethod
    def generate_cnpj():
        cnpj = [random.randrange(10) for _ in range(8)] + [0, 0, 0, 1]

        for _ in range(2):
            value = sum(v * (i % 8 + 2) for i, v in enumerate(reversed(cnpj)))
            digit = 11 - value % 11
            cnpj.append(digit if digit < 10 else 0)

        cnpj_number = "".join(str(x) for x in cnpj)

        cnpj_number = (
            f"{cnpj_number[0:2]}.{cnpj_number[2:5]}.{cnpj_number[5:8]}/{cnpj_number[8:12]}-{cnpj_number[12:14]}"
        )

        return cnpj_number

    # ────────────────────────────────────────────────────────────────
    # CPF SÓ DÍGITOS, para cadastrar parte no Cadastro de verdade
    # (ponto de integração, tests/e2e/). Mesmo comportamento do
    # RandomGenerator.generate_cpf_digits(ending=...) do BootCamp_QiTech_Party.
    # ────────────────────────────────────────────────────────────────
    # O bureau mockado do Cadastro decide pelo final do documento (guia
    # 00 §2): 00 recusa, 99 fica fora do ar, 98 e 97 falham uma vez. Sem
    # `ending`, esses finais são sorteados de novo; com `ending`, o sorteio
    # repete até o documento terminar exatamente nele.
    RESERVED_ENDINGS = ("00", "97", "98", "99")

    @staticmethod
    def _cpf_digits() -> str:
        cpf = [random.randrange(10) for _ in range(9)]
        for _ in range(2):
            value = sum([(len(cpf) + 1 - i) * v for i, v in enumerate(cpf)]) % 11
            cpf.append(11 - value if value > 1 else 0)
        return "".join(str(x) for x in cpf)

    @staticmethod
    def generate_cpf_digits(ending: str = None) -> str:
        while True:
            document_number = RandomGenerator._cpf_digits()

            if ending is None and document_number[-2:] not in RandomGenerator.RESERVED_ENDINGS:
                return document_number

            if ending is not None and document_number.endswith(ending):
                return document_number
