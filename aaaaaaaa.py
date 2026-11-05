"""Processador de consultas SQL para o Projeto 2 de Banco de Dados.

O programa recebe consultas SELECT com FROM, JOIN, ON e WHERE, valida a
consulta contra os metadados do enunciado, mostra a algebra relacional e
monta os grafos de operadores original e otimizado.

Execute com:
    py aaaaaaaa.py

Para validar rapidamente as quatro consultas de exemplo sem abrir a janela:
    py aaaaaaaa.py --self-check
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Iterable


# ---------------------------------------------------------------------------
# Metadados fornecidos no Modelo Relacional do enunciado
# ---------------------------------------------------------------------------

SCHEMA: dict[str, tuple[str, tuple[str, ...]]] = {
    "categoria": ("Categoria", ("idCategoria", "Descricao")),
    "produto": (
        "Produto",
        (
            "idProduto",
            "Nome",
            "Descricao",
            "Preco",
            "QuantEstoque",
            "Categoria_idCategoria",
        ),
    ),
    "tipocliente": ("TipoCliente", ("idTipoCliente", "Descricao")),
    "cliente": (
        "Cliente",
        (
            "idCliente",
            "Nome",
            "Email",
            "Nascimento",
            "Senha",
            "TipoCliente_idTipoCliente",
            "DataRegistro",
        ),
    ),
    "tipoendereco": ("TipoEndereco", ("idTipoEndereco", "Descricao")),
    "endereco": (
        "Endereco",
        (
            "idEndereco",
            "EnderecoPadrao",
            "Logradouro",
            "Numero",
            "Complemento",
            "Bairro",
            "Cidade",
            "UF",
            "CEP",
            "TipoEndereco_idTipoEndereco",
            "Cliente_idCliente",
        ),
    ),
    "telefone": ("Telefone", ("Numero", "Cliente_idCliente")),
    "status": ("Status", ("idStatus", "Descricao")),
    "pedido": (
        "Pedido",
        (
            "idPedido",
            "Status_idStatus",
            "DataPedido",
            "ValorTotalPedido",
            "Cliente_idCliente",
        ),
    ),
    "pedido_has_produto": (
        "Pedido_has_Produto",
        ("idPedidoProduto", "Pedido_idPedido", "Produto_idProduto", "Quantidade", "PrecoUnitario"),
    ),
}


TEST_QUERIES = [
    """SELECT cliente.nome, pedido.idPedido, pedido.DataPedido, pedido.ValorTotalPedido
FROM Cliente JOIN pedido ON cliente.idcliente = pedido.Cliente_idCliente
WHERE cliente.TipoCliente_idTipoCliente = 1 AND pedido.ValorTotalPedido = 0;""",
    """SELECT cliente.nome, pedido.idPedido, pedido.DataPedido, Status.descricao, pedido.ValorTotalPedido
FROM Cliente JOIN pedido ON cliente.idcliente = pedido.Cliente_idCliente
JOIN Status ON Status.idstatus = Pedido.status_idstatus
WHERE Status.descricao = 'Aberto' AND cliente.TipoCliente_idTipoCliente = 1
AND pedido.ValorTotalPedido = 0;""",
    """SELECT cliente.nome, pedido.idPedido, pedido.DataPedido, Status.descricao, pedido.ValorTotalPedido, produto.QuantEstoque
FROM Cliente JOIN pedido ON cliente.idcliente = pedido.Cliente_idCliente
JOIN Status ON Status.idstatus = Pedido.status_idstatus
JOIN pedido_has_produto ON pedido.idPedido = pedido_has_produto.Pedido_idPedido
JOIN produto ON produto.idProduto = pedido_has_produto.Produto_idProduto
WHERE Status.descricao = 'Aberto' AND cliente.TipoCliente_idTipoCliente = 1
AND pedido.ValorTotalPedido = 0 AND produto.QuantEstoque > 0;""",
    """SELECT cliente.nome, tipocliente.descricao, pedido.idPedido, pedido.DataPedido, Status.descricao,
pedido.ValorTotalPedido, categoria.descricao, produto.QuantEstoque
FROM Cliente JOIN pedido ON cliente.idcliente = pedido.Cliente_idCliente
JOIN tipocliente ON cliente.tipocliente_idtipocliente = tipocliente.idTipoCliente
JOIN endereco ON cliente.idcliente = endereco.Cliente_idCliente
JOIN Status ON Status.idstatus = Pedido.status_idstatus
JOIN pedido_has_produto ON pedido.idPedido = pedido_has_produto.Pedido_idPedido
JOIN produto ON produto.idProduto = pedido_has_produto.Produto_idProduto
JOIN categoria ON categoria.idcategoria = produto.Categoria_idCategoria
WHERE Status.descricao = 'Aberto' AND cliente.email = 'Luffy@gmail.com'
AND pedido.ValorTotalPedido = 0 AND produto.preco > 5000 AND endereco.cidade = 'Gramado';""",
]


class SQLSyntaxError(ValueError):
    """Erro na estrutura da SQL."""


class SQLSemanticError(ValueError):
    """Erro de tabela, atributo ou ambiguidade nos metadados."""


@dataclass
class Token:
    kind: str
    text: str
    position: int

    @property
    def upper(self) -> str:
        return self.text.upper()


@dataclass
class TableRef:
    name: str
    alias: str | None = None

    @property
    def key(self) -> str:
        return (self.alias or self.name).lower()

    @property
    def display(self) -> str:
        return self.alias or self.name


@dataclass
class ColumnRef:
    column: str
    qualifier: str | None = None
    table_key: str | None = None
    canonical_column: str | None = None

    def display(self) -> str:
        qualifier = self.qualifier or self.table_key or "?"
        column = self.canonical_column or self.column
        return f"{qualifier}.{column}"


@dataclass
class Literal:
    value: str

    def display(self) -> str:
        return self.value


Operand = ColumnRef | Literal


@dataclass
class Predicate:
    left: ColumnRef
    operator: str
    right: Operand
    origin: str

    def display(self) -> str:
        return f"{self.left.display()} {self.operator} {self.right.display()}"

    def tables(self) -> set[str]:
        tables = {self.left.table_key} if self.left.table_key else set()
        if isinstance(self.right, ColumnRef) and self.right.table_key:
            tables.add(self.right.table_key)
        return tables


@dataclass
class JoinSpec:
    table: TableRef
    predicates: list[Predicate]


@dataclass
class Query:
    select: list[ColumnRef]
    tables: list[TableRef]
    joins: list[JoinSpec]
    where: list[Predicate]


@dataclass
class OperatorNode:
    kind: str
    label: str
    children: list["OperatorNode"] = field(default_factory=list)
    final: bool = False


@dataclass
class AnalysisResult:
    query: Query
    original_algebra: str
    optimized_algebra: str
    original_graph: OperatorNode
    optimized_graph: OperatorNode
    plan: list[str]


# ---------------------------------------------------------------------------
# Lexer e parser para o subconjunto solicitado no enunciado
# ---------------------------------------------------------------------------

TOKEN_PATTERN = re.compile(
    r"(?P<space>\s+)|(?P<string>'(?:''|[^'])*')|(?P<number>\d+(?:\.\d+)?)|"
    r"(?P<operator><=|>=|<>|=|<|>)|(?P<comma>,)|(?P<dot>\.)|(?P<lparen>\()|"
    r"(?P<rparen>\))|(?P<semicolon>;)|(?P<star>\*)|(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)"
)

KEYWORDS = {"SELECT", "FROM", "WHERE", "JOIN", "ON", "AND", "AS"}


def tokenize(sql: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(sql):
        match = TOKEN_PATTERN.match(sql, position)
        if not match:
            excerpt = sql[position : position + 20]
            raise SQLSyntaxError(f"Caractere inválido próximo de: {excerpt!r}")
        position = match.end()
        kind = match.lastgroup or ""
        if kind != "space":
            tokens.append(Token(kind, match.group(), match.start()))
    return tokens


class SQLParser:
    def __init__(self, sql: str) -> None:
        self.tokens = tokenize(sql)
        self.index = 0

    def current(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> Token:
        token = self.current()
        if token is None:
            raise SQLSyntaxError("Fim inesperado da consulta.")
        self.index += 1
        return token

    def accept_keyword(self, keyword: str) -> bool:
        token = self.current()
        if token and token.kind == "identifier" and token.upper == keyword:
            self.index += 1
            return True
        return False

    def expect_keyword(self, keyword: str) -> None:
        if not self.accept_keyword(keyword):
            found = self.current().text if self.current() else "fim da consulta"
            raise SQLSyntaxError(f"Esperado '{keyword}', encontrado '{found}'.")

    def expect_kind(self, kind: str, description: str) -> Token:
        token = self.current()
        if token is None or token.kind != kind:
            found = token.text if token else "fim da consulta"
            raise SQLSyntaxError(f"Esperado {description}, encontrado '{found}'.")
        self.index += 1
        return token

    def parse(self) -> Query:
        if not self.tokens:
            raise SQLSyntaxError("Digite uma consulta SQL antes de analisar.")
        self.expect_keyword("SELECT")
        select_tokens = self.collect_until_keyword("FROM")
        select = self.parse_select_list(select_tokens)
        self.expect_keyword("FROM")
        first_table = self.parse_table_ref()
        tables = [first_table]
        joins: list[JoinSpec] = []
        where: list[Predicate] = []

        while self.current() is not None:
            if self.accept_keyword("JOIN"):
                table = self.parse_table_ref()
                if any(existing.key == table.key for existing in tables):
                    raise SQLSemanticError(f"A tabela ou alias '{table.display}' foi usado mais de uma vez.")
                self.expect_keyword("ON")
                condition_tokens = self.collect_until_boundary({"JOIN", "WHERE"})
                predicates = parse_conditions(condition_tokens, "ON")
                joins.append(JoinSpec(table, predicates))
                tables.append(table)
            elif self.accept_keyword("WHERE"):
                condition_tokens = self.collect_until_semicolon()
                where = parse_conditions(condition_tokens, "WHERE")
                if self.current() is not None:
                    raise SQLSyntaxError("Nada pode aparecer depois da cláusula WHERE.")
                break
            elif self.current() and self.current().kind == "semicolon":
                self.index += 1
                if self.current() is not None:
                    raise SQLSyntaxError("Há conteúdo depois do ponto e vírgula.")
                break
            else:
                found = self.current().text if self.current() else "fim da consulta"
                raise SQLSyntaxError(f"Esperado JOIN, WHERE ou fim da consulta; encontrado '{found}'.")

        if any(table.key == first_table.key for table in tables[1:]):
            raise SQLSemanticError(f"A tabela ou alias '{first_table.display}' foi usado mais de uma vez.")
        query = Query(select, tables, joins, where)
        validate_query(query)
        return query

    def collect_until_keyword(self, keyword: str) -> list[Token]:
        start = self.index
        depth = 0
        while self.current() is not None:
            token = self.current()
            if token.kind == "lparen":
                depth += 1
            elif token.kind == "rparen":
                depth -= 1
            elif depth == 0 and token.kind == "identifier" and token.upper == keyword:
                return self.tokens[start : self.index]
            self.index += 1
        raise SQLSyntaxError(f"A cláusula '{keyword}' é obrigatória.")

    def collect_until_boundary(self, keywords: set[str]) -> list[Token]:
        start = self.index
        depth = 0
        while self.current() is not None:
            token = self.current()
            if token.kind == "lparen":
                depth += 1
            elif token.kind == "rparen":
                depth -= 1
            elif depth == 0 and token.kind == "identifier" and token.upper in keywords:
                break
            elif depth == 0 and token.kind == "semicolon":
                break
            self.index += 1
        return self.tokens[start : self.index]

    def collect_until_semicolon(self) -> list[Token]:
        start = self.index
        while self.current() is not None and self.current().kind != "semicolon":
            self.index += 1
        collected = self.tokens[start : self.index]
        if self.current() and self.current().kind == "semicolon":
            self.index += 1
        return collected

    def parse_table_ref(self) -> TableRef:
        name = self.expect_kind("identifier", "nome de tabela").text
        alias: str | None = None
        if self.accept_keyword("AS"):
            alias = self.expect_kind("identifier", "alias após AS").text
        elif self.current() and self.current().kind == "identifier" and self.current().upper not in KEYWORDS:
            alias = self.take().text
        return TableRef(name, alias)

    def parse_select_list(self, tokens: list[Token]) -> list[ColumnRef]:
        if not tokens:
            raise SQLSyntaxError("SELECT precisa informar ao menos um atributo.")
        groups = split_tokens(tokens, "comma")
        columns: list[ColumnRef] = []
        for group in groups:
            if not group:
                raise SQLSyntaxError("Há uma vírgula sem atributo na lista do SELECT.")
            if len(group) == 1 and group[0].kind == "star":
                raise SQLSyntaxError("Use atributos explícitos no SELECT; '*' não faz parte do escopo do trabalho.")
            operand = parse_operand(group, only_column=True)
            assert isinstance(operand, ColumnRef)
            columns.append(operand)
        return columns


def split_tokens(tokens: list[Token], separator_kind: str) -> list[list[Token]]:
    groups: list[list[Token]] = [[]]
    depth = 0
    for token in tokens:
        if token.kind == "lparen":
            depth += 1
        elif token.kind == "rparen":
            depth -= 1
            if depth < 0:
                raise SQLSyntaxError("Há um ')' sem '(' correspondente.")
        if token.kind == separator_kind and depth == 0:
            groups.append([])
        else:
            groups[-1].append(token)
    if depth != 0:
        raise SQLSyntaxError("Os parênteses da consulta não estão balanceados.")
    return groups


def parse_operand(tokens: list[Token], only_column: bool = False) -> Operand:
    if len(tokens) == 1 and tokens[0].kind in {"string", "number"}:
        if only_column:
            raise SQLSyntaxError("A lista SELECT deve conter atributos, não valores literais.")
        return Literal(tokens[0].text)
    if len(tokens) == 1 and tokens[0].kind == "identifier":
        return ColumnRef(column=tokens[0].text)
    if (
        len(tokens) == 3
        and tokens[0].kind == "identifier"
        and tokens[1].kind == "dot"
        and tokens[2].kind == "identifier"
    ):
        return ColumnRef(column=tokens[2].text, qualifier=tokens[0].text)
    shown = " ".join(token.text for token in tokens)
    raise SQLSyntaxError(f"Atributo ou valor inválido: '{shown}'.")


def parse_conditions(tokens: list[Token], origin: str) -> list[Predicate]:
    if not tokens:
        raise SQLSyntaxError(f"A cláusula {origin} precisa de uma condição.")
    # Parênteses são aceitos para agrupamento com AND. Neste subconjunto não há OR.
    depth = 0
    stripped: list[Token] = []
    for token in tokens:
        if token.kind == "lparen":
            depth += 1
            continue
        if token.kind == "rparen":
            depth -= 1
            if depth < 0:
                raise SQLSyntaxError("Há um ')' sem '(' correspondente.")
            continue
        stripped.append(token)
    if depth:
        raise SQLSyntaxError("Os parênteses da condição não estão balanceados.")
    groups: list[list[Token]] = [[]]
    for token in stripped:
        if token.kind == "identifier" and token.upper == "AND":
            if not groups[-1]:
                raise SQLSyntaxError("AND precisa de uma condição antes dele.")
            groups.append([])
        else:
            groups[-1].append(token)
    if not groups[-1]:
        raise SQLSyntaxError("AND precisa de uma condição depois dele.")

    predicates: list[Predicate] = []
    for group in groups:
        operator_positions = [i for i, token in enumerate(group) if token.kind == "operator"]
        if len(operator_positions) != 1:
            rendered = " ".join(token.text for token in group)
            raise SQLSyntaxError(
                f"Condição inválida '{rendered}'. Use atributo operador atributo/valor."
            )
        operator_index = operator_positions[0]
        left = parse_operand(group[:operator_index], only_column=True)
        right = parse_operand(group[operator_index + 1 :])
        assert isinstance(left, ColumnRef)
        predicates.append(Predicate(left, group[operator_index].text, right, origin))
    return predicates


# ---------------------------------------------------------------------------
# Validação semântica e construção de álgebra relacional
# ---------------------------------------------------------------------------


def validate_query(query: Query) -> None:
    table_by_key: dict[str, TableRef] = {}
    for table in query.tables:
        canonical = table.name.lower()
        if canonical not in SCHEMA:
            raise SQLSemanticError(f"Tabela inexistente no modelo relacional: '{table.name}'.")
        if table.key in table_by_key:
            raise SQLSemanticError(f"Alias duplicado: '{table.display}'.")
        table_by_key[table.key] = table

    for column in query.select:
        resolve_column(column, table_by_key)
    for predicate in all_predicates(query):
        resolve_column(predicate.left, table_by_key)
        if isinstance(predicate.right, ColumnRef):
            resolve_column(predicate.right, table_by_key)


def resolve_column(column: ColumnRef, table_by_key: dict[str, TableRef]) -> None:
    candidates: list[TableRef]
    if column.qualifier:
        requested = column.qualifier.lower()
        candidates = [
            table
            for table in table_by_key.values()
            if table.key == requested or table.name.lower() == requested
        ]
        if not candidates:
            raise SQLSemanticError(
                f"A tabela ou alias '{column.qualifier}' do atributo '{column.qualifier}.{column.column}' não existe na consulta."
            )
    else:
        candidates = list(table_by_key.values())

    matches: list[tuple[TableRef, str]] = []
    for table in candidates:
        _, attributes = SCHEMA[table.name.lower()]
        attribute = next((item for item in attributes if item.lower() == column.column.lower()), None)
        if attribute:
            matches.append((table, attribute))
    if not matches:
        where = f" na tabela '{column.qualifier}'" if column.qualifier else ""
        raise SQLSemanticError(f"Atributo inexistente{where}: '{column.column}'.")
    if len(matches) > 1:
        options = ", ".join(table.display for table, _ in matches)
        raise SQLSemanticError(
            f"Atributo ambíguo '{column.column}'. Qualifique-o com uma destas tabelas: {options}."
        )
    table, attribute = matches[0]
    column.table_key = table.key
    column.canonical_column = attribute
    if column.qualifier is None:
        column.qualifier = table.display


def all_predicates(query: Query) -> Iterable[Predicate]:
    for join in query.joins:
        yield from join.predicates
    yield from query.where


def join_predicate_text(predicates: Iterable[Predicate]) -> str:
    items = [predicate.display() for predicate in predicates]
    return " AND ".join(items) if items else "verdadeiro"


def original_tree(query: Query) -> OperatorNode:
    tree = OperatorNode("table", query.tables[0].display)
    for join in query.joins:
        tree = OperatorNode("join", f"⋈\n{join_predicate_text(join.predicates)}", [tree, OperatorNode("table", join.table.display)])
    if query.where:
        tree = OperatorNode("selection", f"σ\n{join_predicate_text(query.where)}", [tree])
    return OperatorNode("projection", f"π\n{columns_text(query.select)}", [tree], final=True)


def original_algebra(query: Query) -> str:
    expression = query.tables[0].display
    for join in query.joins:
        expression = f"({expression} ⋈_{{{join_predicate_text(join.predicates)}}} {join.table.display})"
    if query.where:
        expression = f"σ_{{{join_predicate_text(query.where)}}}({expression})"
    return f"π_{{{columns_text(query.select)}}}({expression})"


def columns_text(columns: Iterable[ColumnRef]) -> str:
    return ", ".join(column.display() for column in columns)


def predicate_score(predicate: Predicate) -> int:
    # Igualdades em chaves/identificadores tendem a ser mais seletivas.
    score = 1
    for operand in (predicate.left, predicate.right):
        if isinstance(operand, ColumnRef) and operand.canonical_column:
            if operand.canonical_column.lower().startswith("id"):
                score += 2
        elif isinstance(operand, Literal):
            score += 2
    if predicate.operator == "=":
        score += 2
    return score


def build_optimized_tree(query: Query) -> OperatorNode:
    local_filters: dict[str, list[Predicate]] = {table.key: [] for table in query.tables}
    join_filters: list[Predicate] = []
    for predicate in all_predicates(query):
        tables = predicate.tables()
        if len(tables) == 1:
            local_filters[next(iter(tables))].append(predicate)
        else:
            join_filters.append(predicate)

    required_columns: dict[str, list[ColumnRef]] = {table.key: [] for table in query.tables}
    for column in query.select:
        add_required_column(required_columns, column)
    for predicate in all_predicates(query):
        add_required_column(required_columns, predicate.left)
        if isinstance(predicate.right, ColumnRef):
            add_required_column(required_columns, predicate.right)

    def table_score(table: TableRef) -> int:
        return sum(predicate_score(item) for item in local_filters[table.key])

    remaining = sorted(query.tables, key=table_score, reverse=True)
    first = remaining.pop(0)
    included = {first.key}
    tree = filtered_table_node(first, local_filters[first.key], required_columns[first.key])

    # Só escolhe junções que conectam a árvore atual a uma tabela ainda não lida.
    # Isso preserva as dependências e evita produto cartesiano em consultas conectadas.
    while remaining:
        choices: list[tuple[int, TableRef, list[Predicate]]] = []
        for table in remaining:
            connecting = [
                predicate
                for predicate in join_filters
                if table.key in predicate.tables() and predicate.tables() & included
            ]
            if connecting:
                score = sum(predicate_score(item) for item in connecting) + table_score(table)
                choices.append((score, table, connecting))
        if choices:
            _, next_table, connecting = max(choices, key=lambda item: item[0])
            tree = OperatorNode(
                "join",
                f"⋈\n{join_predicate_text(connecting)}",
                [tree, filtered_table_node(next_table, local_filters[next_table.key], required_columns[next_table.key])],
            )
        else:
            # Uma consulta desconexa não permite evitar produto cartesiano. A interface
            # deixa o fato explícito em vez de fingir que há condição de junção.
            next_table = max(remaining, key=table_score)
            tree = OperatorNode(
                "product",
                "×\nSem predicado de junção",
                [tree, filtered_table_node(next_table, local_filters[next_table.key], required_columns[next_table.key])],
            )
        remaining.remove(next_table)
        included.add(next_table.key)

    return OperatorNode("projection", f"π\n{columns_text(query.select)}", [tree], final=True)


def add_required_column(required_columns: dict[str, list[ColumnRef]], column: ColumnRef) -> None:
    if not column.table_key:
        return
    bucket = required_columns[column.table_key]
    identity = (column.table_key, (column.canonical_column or column.column).lower())
    if all(
        (existing.table_key, (existing.canonical_column or existing.column).lower()) != identity
        for existing in bucket
    ):
        bucket.append(column)


def filtered_table_node(table: TableRef, filters: list[Predicate], required: list[ColumnRef]) -> OperatorNode:
    node = OperatorNode("table", table.display)
    if filters:
        node = OperatorNode("selection", f"σ\n{join_predicate_text(filters)}", [node])
    if required:
        node = OperatorNode("projection", f"π\n{columns_text(required)}", [node])
    return node


def algebra_from_tree(node: OperatorNode) -> str:
    if node.kind == "table":
        return node.label
    if node.kind == "selection":
        return f"σ_{{{node.label.split(chr(10), 1)[1]}}}({algebra_from_tree(node.children[0])})"
    if node.kind == "projection":
        return f"π_{{{node.label.split(chr(10), 1)[1]}}}({algebra_from_tree(node.children[0])})"
    operator = "⋈" if node.kind == "join" else "×"
    condition = node.label.split(chr(10), 1)[1]
    suffix = f"_{{{condition}}}" if node.kind == "join" else ""
    return f"({algebra_from_tree(node.children[0])} {operator}{suffix} {algebra_from_tree(node.children[1])})"


def execution_plan(root: OperatorNode) -> list[str]:
    steps: list[str] = []

    def visit(node: OperatorNode) -> None:
        for child in node.children:
            visit(child)
        number = len(steps) + 1
        if node.kind == "table":
            text = f"Ler a tabela {node.label}."
        elif node.kind == "selection":
            condition = node.label.split("\n", 1)[1]
            text = f"Aplicar seleção [{condition}] para reduzir tuplas antes das junções."
        elif node.kind == "projection":
            attributes = node.label.split("\n", 1)[1]
            if node.final:
                text = f"Aplicar projeção final [{attributes}] e entregar o resultado."
            else:
                text = f"Projetar somente [{attributes}] para reduzir atributos intermediários."
        elif node.kind == "join":
            condition = node.label.split("\n", 1)[1]
            text = f"Executar junção [{condition}] com os resultados já reduzidos."
        else:
            text = "Executar produto cartesiano: não foi encontrada condição de junção entre os conjuntos."
        steps.append(f"{number}. {text}")

    visit(root)
    return steps


def analyze_sql(sql: str) -> AnalysisResult:
    query = SQLParser(sql).parse()
    unoptimized = original_tree(query)
    optimized = build_optimized_tree(query)
    return AnalysisResult(
        query=query,
        original_algebra=original_algebra(query),
        optimized_algebra=algebra_from_tree(optimized),
        original_graph=unoptimized,
        optimized_graph=optimized,
        plan=execution_plan(optimized),
    )


# ---------------------------------------------------------------------------
# Interface gráfica e desenho dos grafos
# ---------------------------------------------------------------------------

NODE_COLORS = {
    "table": "#D7EAFE",
    "selection": "#FDE9B8",
    "projection": "#D9F7E8",
    "join": "#E6DAFD",
    "product": "#FFD7D7",
}


class GraphView(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background="white", highlightthickness=0)
        horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        vertical = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def draw(self, root: OperatorNode) -> None:
        self.canvas.delete("all")
        leaves = max(count_leaves(root), 1)
        depth = max(tree_depth(root), 1)
        width = max(900, leaves * 260)
        height = max(380, depth * 145 + 100)
        positions: dict[int, tuple[float, float]] = {}
        next_leaf = [0]

        def locate(node: OperatorNode, level: int) -> float:
            if not node.children:
                x = 110 + next_leaf[0] * 240
                next_leaf[0] += 1
            else:
                child_x = [locate(child, level + 1) for child in node.children]
                x = sum(child_x) / len(child_x)
            positions[id(node)] = (x, 65 + level * 130)
            return x

        locate(root, 0)

        def render_edges(node: OperatorNode) -> None:
            x, y = positions[id(node)]
            for child in node.children:
                cx, cy = positions[id(child)]
                self.canvas.create_line(x, y + 28, cx, cy - 28, arrow=tk.LAST, width=2, fill="#566573")
                render_edges(child)

        def render_nodes(node: OperatorNode) -> None:
            x, y = positions[id(node)]
            lines = node.label.split("\n")
            longest = max(len(line) for line in lines)
            box_width = min(max(150, longest * 7.2 + 22), 360)
            box_height = 50 + (len(lines) - 1) * 19
            color = NODE_COLORS[node.kind]
            self.canvas.create_rectangle(
                x - box_width / 2,
                y - box_height / 2,
                x + box_width / 2,
                y + box_height / 2,
                fill=color,
                outline="#34495E",
                width=2,
            )
            self.canvas.create_text(
                x,
                y,
                text=node.label,
                width=box_width - 14,
                justify="center",
                font=("Segoe UI", 10, "bold" if node.kind != "table" else "normal"),
            )
            for child in node.children:
                render_nodes(child)

        render_edges(root)
        render_nodes(root)
        self.canvas.configure(scrollregion=(0, 0, width, height))


def count_leaves(node: OperatorNode) -> int:
    return 1 if not node.children else sum(count_leaves(child) for child in node.children)


def tree_depth(node: OperatorNode) -> int:
    return 1 if not node.children else 1 + max(tree_depth(child) for child in node.children)


class QueryProcessorApp(ttk.Frame):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=12)
        self.root = root
        root.title("Projeto 2 - Processador de Consultas")
        root.geometry("1380x880")
        root.minsize(1000, 700)
        self.pack(fill="both", expand=True)
        self._build_interface()
        self.load_example(0)

    def _build_interface(self) -> None:
        heading = ttk.Label(
            self,
            text="Processador de Consultas SQL",
            font=("Segoe UI", 18, "bold"),
        )
        heading.pack(anchor="w")
        ttk.Label(
            self,
            text="Subconjunto aceito: SELECT, FROM, JOIN, ON, WHERE, AND e operadores de comparação.",
        ).pack(anchor="w", pady=(0, 8))

        query_frame = ttk.LabelFrame(self, text="Consulta SQL", padding=8)
        query_frame.pack(fill="x")
        self.sql_text = tk.Text(query_frame, height=9, wrap="word", font=("Consolas", 10))
        self.sql_text.pack(fill="x")

        buttons = ttk.Frame(query_frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Analisar consulta", command=self.analyze).pack(side="left")
        ttk.Button(buttons, text="Limpar", command=self.clear).pack(side="left", padx=(8, 0))
        ttk.Label(buttons, text="Consultas de teste:").pack(side="left", padx=(24, 6))
        for index in range(len(TEST_QUERIES)):
            ttk.Button(
                buttons,
                text=str(index + 1),
                width=3,
                command=lambda value=index: self.load_example(value),
            ).pack(side="left", padx=2)

        self.status = ttk.Label(self, text="", font=("Segoe UI", 10, "bold"))
        self.status.pack(anchor="w", pady=(8, 5))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        algebra_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(algebra_tab, text="Álgebra relacional")
        ttk.Label(algebra_tab, text="Álgebra relacional original", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.original_algebra = self.make_readonly_text(algebra_tab, 6)
        self.original_algebra.pack(fill="x", pady=(3, 12))
        ttk.Label(algebra_tab, text="Álgebra relacional otimizada", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.optimized_algebra = self.make_readonly_text(algebra_tab, 9)
        self.optimized_algebra.pack(fill="both", expand=True, pady=(3, 0))

        original_tab = ttk.Frame(self.notebook)
        self.notebook.add(original_tab, text="Grafo original")
        self.original_graph = GraphView(original_tab)
        self.original_graph.pack(fill="both", expand=True)

        optimized_tab = ttk.Frame(self.notebook)
        self.notebook.add(optimized_tab, text="Grafo otimizado")
        self.optimized_graph = GraphView(optimized_tab)
        self.optimized_graph.pack(fill="both", expand=True)

        plan_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(plan_tab, text="Plano de execução")
        ttk.Label(
            plan_tab,
            text="A ordem abaixo é um percurso pós-ordem do grafo otimizado.",
        ).pack(anchor="w", pady=(0, 6))
        self.plan_text = self.make_readonly_text(plan_tab, 18)
        self.plan_text.pack(fill="both", expand=True)

        metadata_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(metadata_tab, text="Metadados")
        metadata = self.make_readonly_text(metadata_tab, 22)
        metadata.pack(fill="both", expand=True)
        insert_text(metadata, metadata_text())

    @staticmethod
    def make_readonly_text(parent: tk.Misc, height: int) -> tk.Text:
        return tk.Text(parent, height=height, wrap="word", font=("Consolas", 10), state="disabled")

    def load_example(self, index: int) -> None:
        self.sql_text.delete("1.0", tk.END)
        self.sql_text.insert("1.0", TEST_QUERIES[index])
        self.status.configure(text=f"Consulta de teste {index + 1} carregada.", foreground="#1F618D")

    def clear(self) -> None:
        self.sql_text.delete("1.0", tk.END)
        self.status.configure(text="Consulta limpa.", foreground="#1F618D")

    def analyze(self) -> None:
        sql = self.sql_text.get("1.0", "end").strip()
        try:
            result = analyze_sql(sql)
        except (SQLSyntaxError, SQLSemanticError) as error:
            self.status.configure(text=f"Erro {'sintático' if isinstance(error, SQLSyntaxError) else 'semântico'}: {error}", foreground="#B03A2E")
            return
        except Exception as error:  # proteção para não fechar a interface em um erro inesperado
            self.status.configure(text=f"Erro inesperado: {error}", foreground="#B03A2E")
            return

        insert_text(self.original_algebra, result.original_algebra)
        insert_text(self.optimized_algebra, result.optimized_algebra)
        insert_text(self.plan_text, "\n\n".join(result.plan))
        self.original_graph.draw(result.original_graph)
        self.optimized_graph.draw(result.optimized_graph)
        self.status.configure(
            text="Consulta válida. Álgebra, grafos e plano de execução foram gerados.",
            foreground="#1E8449",
        )
        self.notebook.select(0)


def insert_text(widget: tk.Text, text: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", tk.END)
    widget.insert("1.0", text)
    widget.configure(state="disabled")


def metadata_text() -> str:
    lines = ["Tabelas e atributos usados na validação:\n"]
    for _, (name, attributes) in SCHEMA.items():
        lines.append(f"{name}({', '.join(attributes)})")
    return "\n".join(lines)


def self_check() -> int:
    for number, sql in enumerate(TEST_QUERIES, start=1):
        result = analyze_sql(sql)
        print(f"Consulta {number}: OK")
        print(f"  Atributos no SELECT: {len(result.query.select)}")
        print(f"  Passos do plano: {len(result.plan)}")
    return 0


def main() -> None:
    if "--self-check" in sys.argv:
        raise SystemExit(self_check())
    root = tk.Tk()
    QueryProcessorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
