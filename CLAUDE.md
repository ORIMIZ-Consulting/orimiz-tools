# House rules for My-Tools

Claude reads this file at the start of every session in this repository.

## Layout

- One tool per top-level folder, named in lowercase with dashes (for example `fel1-lng-cost`).
- Each tool has: `README.md`, `requirements.txt`, a Python package, `tests/`, and at least one example.
- Add every new tool to the table in the root `README.md`.

## Data and sources

- Use public data and published methods only. Never add client data, employer data, or anything marked confidential.
- Every number in a data file needs a `source_url`. If a figure is derived, say how in a `notes` column.
- Say what a cost figure covers (its scope) and its year. Do not mix scopes silently.
- Private user data goes in files starting with `private_`. These are git-ignored. Never commit them.

## Method

- A tool that has a guideline in `docs/` must follow it. Every method choice is a switch with options, a default and a source, and every switch goes into the decision log.

## Code

- Python 3.10 or newer. Keep dependencies few.
- Explain each method at the top of its module: the formula, its source, and its limits.
- Every method has tests. Run `pytest` in the tool's folder before committing.

## Writing

- Write for engineers and managers who are not programmers.
- Plain verbs, short sentences, one idea at a time. Grade 8 to 10 reading level.
- Specific facts over adjectives. No marketing language.
- Avoid em dashes.
- State limits plainly. Every tool says whether it is a screening tool or more.
