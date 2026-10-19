# Judge legality leniently, flag notation strictly

The LLM's answer is judged in two separate steps. Legality uses python-chess's `parse_san` as written, which also accepts UCI (`g1f3`), long-form SAN (`Ng1f3`) and a wrong check sign (`Nf3+`): if it parses to a legal move, the move is played. Notation is then checked strictly: if the answer is not exactly the move's standard SAN (`board.san(move)`, check and mate signs included), the move is recorded and shown as a **Notation slip**. We chose this so the Legal-move streak measures chess knowledge rather than format compliance, while still keeping a full record of format compliance. It also settles a gap in the v1 spec, which ruled out "accepting UCI as a fallback" even though `parse_san` already accepts UCI.

## Considered Options

- **Reject anything that isn't exact SAN as an illegal move**: one rule, but a correct move in the wrong spelling would end the Legal-move streak and use up a retry, mixing up notation with chess.
- **Accept leniently and record nothing**: simplest, but hides how often a model ignores the requested notation.
- **Lenient flag that ignores `+`/`#`**: fewer slips, but "standard SAN" would mean something different from the SAN in the allowed list under Enforced decoding.

## Consequences

- The same judge applies under all LLM constraints, so Free and Listed games are measured with the same ruler.
- Under Blind enforced and Listed enforced the allowed moves are exactly the standard SAN strings, so a Notation slip cannot occur there.
- A Notation slip does not end the Legal-move streak and does not cost a retry.
