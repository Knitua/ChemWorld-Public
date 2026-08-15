#!/usr/bin/env python3
# ruff: noqa: E501
"""Build and validate promotional visuals derived from public v0.4 evidence.

This builder is deliberately separate from ``build_readme_visuals.py``.  The
existing builder owns scientific evidence figures; this module owns only the
README launch assets and records the frozen sources behind every quantitative
label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from chemworld.lab.agent_run import agent_catalog
from chemworld.tasks import list_tasks

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "docs" / "assets" / "readme"
EVIDENCE_SOURCE = ROOT / "evidence" / "derived" / "representative-behavior-and-forks.json"
RELEASE_MANIFEST = ROOT / "release" / "manifest.json"
HERO = ASSET_ROOT / "chemworld-launch-hero.png"
ANIMATION = ASSET_ROOT / "lab-lifecycle.gif"
TRIPTYCH = ASSET_ROOT / "chemworld-three-ways.svg"
PROOF_STRIP = ASSET_ROOT / "public-proof.svg"
METADATA = ASSET_ROOT / "showcase-metadata.json"

TEAL = "#087F73"
TEAL_DARK = "#064E49"
MINT = "#DDF3EB"
PAPER = "#FBF8F0"
INK = "#16332F"
MUTED = "#5B706B"
CORAL = "#F47B62"
LINE = "#B8D6CF"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def public_counts() -> dict[str, int]:
    evidence = read_json(EVIDENCE_SOURCE)
    manifest = read_json(RELEASE_MANIFEST)
    expected = manifest["headline_denominators"]
    actions = evidence["agent_lifecycle"]["actions"]
    fork_pairs = evidence["controlled_world_forks"]["pairs"]
    counts = {
        "public_tasks": len(list_tasks()),
        "reference_units": int(expected["reference_task_world_units"][0]),
        "generated_compositions": int(expected["generated_compositions"][0]),
        "fork_pairs": len(fork_pairs),
        "fork_traces": int(expected["controlled_world_fork_traces"][0]),
        "provider_free_policies": len(agent_catalog()),
        "agent_actions": len(actions),
    }
    required = {
        "public_tasks": 15,
        "reference_units": 64,
        "generated_compositions": 52,
        "fork_pairs": 6,
        "fork_traces": 24,
        "provider_free_policies": 8,
        "agent_actions": 15,
    }
    if counts != required:
        raise RuntimeError(f"public showcase census changed: {counts!r}")
    return counts


def svg_header(width: int, height: int, title: str, description: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f"<title id=\"title\">{title}</title>",
        f"<desc id=\"desc\">{description}</desc>",
        "<defs>",
        '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#16332F" flood-opacity=".10"/></filter>',
        '<linearGradient id="vessel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#56D0B0"/><stop offset="1" stop-color="#087F73"/></linearGradient>',
        "</defs>",
    ]


def triptych_svg(counts: dict[str, int]) -> str:
    parts = svg_header(
        1500,
        560,
        "Three ways to enter ChemWorld",
        "Student Lab, Agent Observatory and programmable worlds, all bound to the public runtime.",
    )
    parts.extend(
        [
            f'<rect width="1500" height="560" rx="32" fill="{PAPER}"/>',
            f'<text x="60" y="70" font-family="Inter,Arial,sans-serif" font-size="18" font-weight="700" letter-spacing="3" fill="{TEAL}">THREE WAYS IN</text>',
            f'<text x="60" y="118" font-family="Georgia,serif" font-size="34" font-weight="700" fill="{INK}">Operate. Observe. Change the world.</text>',
        ]
    )
    panels = [
        (54, "01", "STUDENT LAB", "Operate the apparatus", f"{counts['public_tasks']} typed public tasks"),
        (526, "02", "AGENT OBSERVATORY", "Watch decisions unfold", f"{counts['provider_free_policies']} provider-free policies"),
        (998, "03", "PROGRAMMABLE WORLDS", "Replay controlled change", f"{counts['fork_pairs']} fork pairs · {counts['fork_traces']} traces"),
    ]
    for index, (x, number, label, title, note) in enumerate(panels):
        parts.extend(
            [
                f'<rect x="{x}" y="158" width="448" height="342" rx="24" fill="#FFFFFF" stroke="{LINE}" filter="url(#shadow)"/>',
                f'<circle cx="{x + 46}" cy="202" r="22" fill="{MINT}"/>',
                f'<text x="{x + 46}" y="209" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="14" font-weight="800" fill="{TEAL}">{number}</text>',
                f'<text x="{x + 82}" y="207" font-family="Inter,Arial,sans-serif" font-size="13" font-weight="800" letter-spacing="2" fill="{TEAL}">{label}</text>',
            ]
        )
        if index == 0:
            parts.extend(
                [
                    f'<path d="M{x+174} 246v30h-16v98c0 44 26 72 68 72s68-28 68-72v-98h-16v-30" fill="none" stroke="{TEAL_DARK}" stroke-width="6" stroke-linecap="round"/>',
                    f'<path d="M{x+161} 365h130c-1 48-23 77-65 77s-64-29-65-77z" fill="url(#vessel)" opacity=".92"/>',
                    f'<circle cx="{x+340}" cy="306" r="10" fill="{CORAL}"/>',
                    f'<path d="M{x+330} 306h-34" stroke="{CORAL}" stroke-width="4" stroke-linecap="round"/>',
                ]
            )
        elif index == 1:
            for step in range(5):
                sx = x + 92 + step * 65
                parts.append(f'<circle cx="{sx}" cy="320" r="18" fill="{MINT if step != 3 else CORAL}" stroke="{TEAL}" stroke-width="3"/>')
                if step < 4:
                    parts.append(f'<path d="M{sx+20} 320h25" stroke="{TEAL}" stroke-width="3" stroke-linecap="round"/>')
            parts.extend(
                [
                    f'<rect x="{x+94}" y="374" width="258" height="12" rx="6" fill="{MINT}"/>',
                    f'<rect x="{x+94}" y="374" width="189" height="12" rx="6" fill="{TEAL}"/>',
                    f'<circle cx="{x+367}" cy="380" r="14" fill="{CORAL}"/>',
                ]
            )
        else:
            parts.extend(
                [
                    f'<rect x="{x+72}" y="262" width="120" height="126" rx="18" fill="{MINT}" stroke="{TEAL}" stroke-width="3"/>',
                    f'<rect x="{x+256}" y="262" width="120" height="126" rx="18" fill="#FFF0EB" stroke="{CORAL}" stroke-width="3"/>',
                    f'<path d="M{x+197} 325h52" stroke="{INK}" stroke-width="4" stroke-linecap="round"/>',
                    f'<path d="M{x+236} 312l14 13-14 13" fill="none" stroke="{INK}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
                    f'<path d="M{x+95} 340c25-45 48 44 74-24M{x+279} 340c25-25 48 20 74-48" fill="none" stroke="{TEAL}" stroke-width="4" stroke-linecap="round"/>',
                ]
            )
        parts.extend(
            [
                f'<text x="{x+28}" y="460" font-family="Georgia,serif" font-size="24" font-weight="700" fill="{INK}">{title}</text>',
                f'<text x="{x+28}" y="486" font-family="Inter,Arial,sans-serif" font-size="15" fill="{MUTED}">{note}</text>',
            ]
        )
    parts.append("</svg>\n")
    return "\n".join(parts)


def proof_svg(counts: dict[str, int]) -> str:
    items = [
        (str(counts["public_tasks"]), "PUBLIC TASKS"),
        (str(counts["generated_compositions"]), "QUALIFIED COMPOSITIONS"),
        (f'{counts["fork_pairs"]} / {counts["fork_traces"]}', "FORK PAIRS / TRACES"),
        (str(counts["provider_free_policies"]), "PROVIDER-FREE POLICIES"),
    ]
    parts = svg_header(1500, 220, "ChemWorld public evidence at a glance", "Four frozen public v0.4 counts.")
    parts.extend(
        [
            f'<rect width="1500" height="220" rx="30" fill="{TEAL_DARK}"/>',
            f'<circle cx="1440" cy="-15" r="140" fill="{TEAL}" opacity=".45"/>',
            f'<circle cx="80" cy="230" r="120" fill="{CORAL}" opacity=".20"/>',
        ]
    )
    for index, (value, label) in enumerate(items):
        x = 95 + index * 360
        if index:
            parts.append(f'<line x1="{x-45}" y1="52" x2="{x-45}" y2="168" stroke="#75B9AC" opacity=".45"/>')
        parts.extend(
            [
                f'<text x="{x}" y="112" font-family="Georgia,serif" font-size="55" font-weight="700" fill="#FFFFFF">{value}</text>',
                f'<text x="{x}" y="150" font-family="Inter,Arial,sans-serif" font-size="14" font-weight="700" letter-spacing="1.7" fill="#BCE5DC">{label}</text>',
            ]
        )
    parts.append("</svg>\n")
    return "\n".join(parts)


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def build_animation(evidence: dict[str, Any]) -> None:
    actions = evidence["agent_lifecycle"]["actions"]
    selected = [0, 1, 2, 3, 4, 7, 8, 10, 11, 12, 13, 14]
    labels = {
        "add_reagent": "ADD REAGENT",
        "add_solvent": "ADD SOLVENT",
        "add_catalyst": "ADD CATALYST",
        "heat": "HEAT",
        "measure": "MEASURE",
        "wait": "WAIT",
        "quench": "QUENCH",
        "distill": "DISTILL",
        "collect_fraction": "COLLECT FRACTION",
        "terminate": "TERMINATE",
    }
    frames: list[Image.Image] = []
    for frame_index, action_index in enumerate(selected):
        record = actions[action_index]
        operation = str(record["action"]["operation"])
        image = Image.new("RGB", (1200, 675), PAPER)
        draw = ImageDraw.Draw(image)
        draw.ellipse((900, -160, 1270, 210), fill="#E4F3ED")
        draw.ellipse((-150, 510, 240, 900), fill="#FDE8E1")
        draw.text((58, 48), "PUBLIC v0.4 · DETERMINISTIC SESSION", font=font(19, bold=True), fill=TEAL)
        draw.text((58, 82), "One experiment, precisely replayed", font=font(38, bold=True), fill=INK)
        rounded(draw, (58, 145, 755, 590), 28, "#FFFFFF", LINE, 3)
        rounded(draw, (785, 145, 1142, 590), 28, TEAL_DARK)

        # Apparatus: a stable scene whose public liquid level and signal evolve.
        vessel = (210, 225, 542, 510)
        draw.arc((210, 175, 542, 510), 0, 180, fill=TEAL_DARK, width=7)
        draw.line((210, 335, 210, 425), fill=TEAL_DARK, width=7)
        draw.line((542, 335, 542, 425), fill=TEAL_DARK, width=7)
        draw.arc(vessel, 0, 180, fill=TEAL_DARK, width=7)
        fill_top = 438 - min(frame_index, 8) * 10
        draw.rounded_rectangle((219, fill_top, 533, 467), radius=62, fill="#2DB894")
        draw.line((235, fill_top + 7, 515, fill_top + 7), fill="#83E3CA", width=5)
        draw.line((355, 175, 355, 280), fill=TEAL_DARK, width=7)
        draw.line((397, 175, 397, 280), fill=TEAL_DARK, width=7)
        draw.line((355, 175, 440, 175), fill=TEAL_DARK, width=7)
        draw.ellipse((594, 263, 646, 315), fill=CORAL if operation in {"measure", "terminate"} else "#63CBB0", outline=TEAL_DARK, width=4)
        draw.line((542, 289, 594, 289), fill=TEAL_DARK, width=4)
        draw.text((191, 527), "PUBLIC APPARATUS STATE", font=font(16, bold=True), fill=MUTED)

        draw.text((822, 185), f"STEP {action_index + 1:02d} / 15", font=font(17, bold=True), fill="#9AD6C8")
        draw.text((822, 230), labels.get(operation, operation.upper()), font=font(29, bold=True), fill="#FFFFFF")
        draw.text((822, 283), "VALIDATED", font=font(15, bold=True), fill="#FFC3B6")
        draw.line((822, 324, 1092, 324), fill="#438C81", width=2)
        draw.text((822, 355), "ACT", font=font(14, bold=True), fill="#9AD6C8")
        draw.text((893, 355), "OBSERVE", font=font(14, bold=True), fill="#9AD6C8")
        draw.text((1004, 355), "REPLAY", font=font(14, bold=True), fill="#9AD6C8")
        for step, x in enumerate((836, 929, 1045)):
            active = frame_index >= step * 3
            draw.ellipse((x - 12, 388, x + 12, 412), fill=CORAL if active else "#407C74")
        highlight = str(record.get("observation_highlight") or "")
        signal = "PUBLIC SIGNAL UPDATED" if highlight and highlight != "—" else "STATE TRANSITION COMMITTED"
        draw.text((822, 455), signal, font=font(16, bold=True), fill="#FFFFFF")
        draw.text((822, 492), "No hidden state exposed", font=font(16), fill="#A9D8CE")
        draw.text((822, 525), "Exact trace retained", font=font(16), fill="#A9D8CE")

        bar_y = 618
        draw.rounded_rectangle((58, bar_y, 1142, bar_y + 8), radius=4, fill="#D6E6E1")
        progress = 58 + int(1084 * (frame_index + 1) / len(selected))
        draw.rounded_rectangle((58, bar_y, progress, bar_y + 8), radius=4, fill=TEAL)
        frames.append(image)
    frames[0].save(
        ANIMATION,
        save_all=True,
        append_images=frames[1:],
        duration=600,
        loop=0,
        optimize=True,
        disposal=2,
    )


def metadata_payload(counts: dict[str, int]) -> dict[str, Any]:
    return {
        "schema_version": "chemworld-readme-showcase-1.0",
        "release": "0.4.0",
        "scientific_boundary": "Promotional assets summarize public software evidence; they do not report physical-laboratory validation or agent rankings.",
        "sources": {
            "representative_behavior": {
                "path": EVIDENCE_SOURCE.relative_to(ROOT).as_posix(),
                "sha256": sha256(EVIDENCE_SOURCE),
            },
            "release_manifest": {
                "path": RELEASE_MANIFEST.relative_to(ROOT).as_posix(),
                "release": "0.4.0",
                "binding": "semantic counts; the manifest hashes this metadata file",
            },
        },
        "counts": counts,
        "assets": {
            "hero": {
                "path": HERO.relative_to(ROOT).as_posix(),
                "kind": "conceptual brand illustration",
                "source": "OpenAI image generation; no experimental outcomes encoded",
            },
            "animation": {
                "path": ANIMATION.relative_to(ROOT).as_posix(),
                "kind": "stylized deterministic public lifecycle",
                "source_steps": [1, 2, 3, 4, 5, 8, 9, 11, 12, 13, 14, 15],
            },
            "triptych": {"path": TRIPTYCH.relative_to(ROOT).as_posix()},
            "proof_strip": {"path": PROOF_STRIP.relative_to(ROOT).as_posix()},
        },
    }


def verify_visuals(counts: dict[str, int]) -> None:
    required = (HERO, ANIMATION, TRIPTYCH, PROOF_STRIP, METADATA)
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing README showcase assets: {missing}")

    with Image.open(HERO) as hero:
        if hero.width < 1500 or hero.height < 700 or not 1.9 <= hero.width / hero.height <= 2.1:
            raise RuntimeError(f"hero dimensions are not a wide 2:1 composition: {hero.size}")
    if HERO.stat().st_size > 4 * 1024 * 1024:
        raise RuntimeError("hero exceeds 4 MiB")

    with Image.open(ANIMATION) as animation:
        frames = int(getattr(animation, "n_frames", 1))
        durations: list[int] = []
        for index in range(frames):
            animation.seek(index)
            durations.append(int(animation.info.get("duration", 0)))
        if animation.size != (1200, 675):
            raise RuntimeError(f"animation dimensions changed: {animation.size}")
        if not 10 <= frames <= 16:
            raise RuntimeError(f"animation frame count changed: {frames}")
        if not 6000 <= sum(durations) <= 8000:
            raise RuntimeError(f"animation duration must be 6-8 seconds: {sum(durations)} ms")
    if ANIMATION.stat().st_size >= 4 * 1024 * 1024:
        raise RuntimeError("animation exceeds 4 MiB")

    expected_triptych = triptych_svg(counts)
    expected_proof = proof_svg(counts)
    if TRIPTYCH.read_text(encoding="utf-8") != expected_triptych:
        raise RuntimeError("README triptych is stale; run scripts/build_readme_showcase.py")
    if PROOF_STRIP.read_text(encoding="utf-8") != expected_proof:
        raise RuntimeError("README proof strip is stale; run scripts/build_readme_showcase.py")
    expected_metadata = json.dumps(metadata_payload(counts), indent=2, ensure_ascii=False) + "\n"
    if METADATA.read_text(encoding="utf-8") != expected_metadata:
        raise RuntimeError("README showcase metadata is stale")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without rewriting assets")
    args = parser.parse_args()
    counts = public_counts()
    if not args.check:
        ASSET_ROOT.mkdir(parents=True, exist_ok=True)
        evidence = read_json(EVIDENCE_SOURCE)
        TRIPTYCH.write_text(triptych_svg(counts), encoding="utf-8")
        PROOF_STRIP.write_text(proof_svg(counts), encoding="utf-8")
        build_animation(evidence)
        METADATA.write_text(
            json.dumps(metadata_payload(counts), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    verify_visuals(counts)
    print(
        "README showcase verified: "
        f"{counts['public_tasks']} tasks, {counts['generated_compositions']} compositions, "
        f"{counts['fork_pairs']} fork pairs/{counts['fork_traces']} traces, "
        f"{counts['provider_free_policies']} policies"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
