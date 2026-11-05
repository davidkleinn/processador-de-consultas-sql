# Processador de Consultas SQL

Projeto acadêmico da disciplina de Banco de Dados. A aplicação demonstra, de forma visual, como um SGBD interpreta e organiza uma consulta SQL antes de executá-la.

> **Escopo didático:** o programa não se conecta a um banco de dados real. Ele valida a consulta com base nos metadados do enunciado e produz representações e um plano de execução teórico.

## Funcionalidades

- Interface gráfica desenvolvida com **Tkinter**.
- Análise de consultas com SELECT, FROM, JOIN ... ON e WHERE.
- Suporte aos operadores de comparação =, >, <, <=, >= e <>, unidos por AND e parênteses.
- Validação sintática e semântica, com identificação separada de erros de sintaxe e de tabelas, atributos ou apelidos inválidos.
- Conversão da SQL para **Álgebra Relacional**.
- Exibição da árvore de operadores original e da árvore otimizada.
- Otimização com antecipação de seleções, redução de atributos por projeção, priorização de filtros mais restritivos e junções sem produto cartesiano.
- Geração de um plano de execução ordenado, explicando a heurística usada em cada etapa.

## Tecnologias

- Python 3
- Tkinter (biblioteca gráfica padrão do Python)
- Bibliotecas padrão do Python — não há dependências externas

## Como executar

```bash
git clone https://github.com/davidkleinn/processador-de-consultas-sql.git
cd processador-de-consultas-sql
py aaaaaaaa.py
```

Em ambientes em que o comando py não estiver disponível, use:

```bash
python aaaaaaaa.py
```

## Como usar

1. Execute o programa.
2. Escolha uma das consultas de exemplo (botões 1 a 4) ou escreva uma SQL no campo de entrada.
3. Clique em **Analisar consulta**.
4. Consulte as abas para acompanhar a validação, a álgebra relacional, as árvores de operadores e o plano de execução.

## Subconjunto de SQL aceito

A aplicação foi construída para o escopo do projeto e aceita consultas no formato:

```sql
SELECT tabela.atributo
FROM Tabela
JOIN OutraTabela ON Tabela.chave = OutraTabela.chave
WHERE atributo = valor AND outro_atributo > valor;
```

Os nomes de tabelas e atributos são verificados de acordo com o modelo lógico fornecido no enunciado. Palavras-chave não diferenciam maiúsculas de minúsculas e espaços extras são ignorados.

## Etapas demonstradas

1. **Tokenização e parsing:** a SQL é separada em tokens e estruturada em uma representação interna.
2. **Validação semântica:** são conferidos tabelas, atributos, qualificadores e compatibilidade dos operadores.
3. **Álgebra relacional:** a consulta é convertida para seleções (σ), projeções (π) e junções (⋈).
4. **Otimização:** filtros são antecipados, atributos desnecessários são eliminados e junções são organizadas por prioridade.
5. **Plano de execução:** cada operação é apresentada em uma ordem que explica o motivo da escolha.

## Organização do código

O projeto é composto por um único arquivo:

- **aaaaaaaa.py** — contém o catálogo do esquema, o analisador SQL, a validação semântica, a geração e otimização de álgebra relacional, o desenho das árvores e a interface gráfica.

## Teste rápido

Para executar automaticamente as quatro consultas de exemplo, sem abrir a interface gráfica:

```bash
py aaaaaaaa.py --self-check
```

O comando valida parsing, semântica, geração da álgebra relacional, árvore original, árvore otimizada e plano de execução para cada exemplo.

## Critérios do projeto contemplados

- Interface para entrada da consulta e visualização dos resultados.
- Parsing e validação sintática e semântica.
- Geração de álgebra relacional e grafo de operadores.
- Otimização de seleção, projeção e junção.
- Plano de execução explicável e ordenado.

## Autoria

Desenvolvido como entrega acadêmica do **Projeto 2 — Processador de Consultas** da disciplina de Banco de Dados.
