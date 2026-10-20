# Engineering notes

## Grammar

```text
expression := prefix (operator expression)*
prefix     := number | cell | range | function-call | '(' expression ')' | ('+'|'-') expression
range      := cell ':' cell
function   := SUM | AVG | MIN | MAX | ABS | ROUND | IF
```

Binding powers: addition/subtraction 10, multiplication/division 20, unary sign 25, exponent 30. Exponentiation is right associative. Input length, range area, exponent magnitude and ROUND precision are bounded. Supported formula names are allowlisted. Blank inputs evaluate to zero; missing numeric references also evaluate to zero.

## An edit through the system

The client sends `{type: "edit", cell, raw, base_revision, op}`. `op` correlates acknowledgements with local timers; it is not a durable idempotency key. The UI waits for server results and does not apply optimistic values.

Under a single process-wide authority lock, the server compares revisions and rejects stale writes. Parsing and cycle checks run before graph mutation. A proposed cell's dependencies must not reach the cell itself. The old reverse edges are removed and new reverse edges added only after validation.

An affected-subgraph traversal followed by Kahn ordering updates values. Formula evaluation failures such as divide-by-zero become cell errors and propagate; syntax errors and circular references reject the edit. The SQL transaction stores input, revision, and audit event atomically. A failed SQL transaction reloads durable cell inputs. After commit, the authority broadcasts the affected patch and database event sequence.

The lock currently also covers broadcasts (with bounded per-client sends), which simplifies ordering at the cost of head-of-line blocking. Production scaling should move delivery to ordered, bounded per-client queues, disconnect slow consumers, and preserve sequence ordering. The present server intentionally favors understandable consistency over maximum throughput.

## Costs and tradeoffs

Dependency discovery costs O(reachable graph) for cycle checking. Affected evaluation costs O(Va + Ea + expression work). Snapshot generation and serialization still cost O(total cells); incremental calculation does not make all server work incremental. Reloading a workbook inserts inputs through the normal engine path, favoring simplicity over bulk-load speed.

Decimal uses the default 28-digit context. This avoids binary floating-point surprises but is not an accounting policy; real products need explicit precision, scale, currency, and rounding specifications.

Current schema models a single workbook; cell address is its primary key. Multi-workbook support needs workbook IDs in all keys, membership checks, per-workbook graph lifecycle, and workbook-specific locks/sequencers.

## Failure model

- Disconnect before acknowledgement: transaction outcome is unknown; reconnect snapshot wins. No blind retry.
- Concurrent writes: first matching revision commits; stale contenders see a conflict snapshot.
- Cycle: reject the input and preserve prior graph/state.
- Invalid dependent arithmetic: expose an error value and allow later inputs to repair it.
- Process restart: rebuild graph and values from durable raw inputs and revisions.
- Database failure: reject the edit, reload durable state, and do not broadcast a successful commit.

## Next worthwhile work

Implement transactional outbox delivery, durable idempotency keys, per-workbook authorization, SQL migrations, property-based parser tests, PostgreSQL integration CI, authenticated browser tests. These are meaningful extensions, not completed features.
