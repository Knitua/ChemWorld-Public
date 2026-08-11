"""Run a random ChemWorld baseline from Python."""

from chemworld.eval.runner import make_agent, run_agent


def main() -> None:
    agent = make_agent("random")
    history = run_agent(
        env_id="ChemWorld",
        agent=agent,
        world_split="public-dev",
        budget=10,
        objective="balanced",
        seed=42,
        output_path="runs/example_random.jsonl",
    )
    print(f"completed {len(history)} operations")


if __name__ == "__main__":
    main()

