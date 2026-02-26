# 🐮 Cow Language Implementations

Welcome to the Cow Language folder! All scripts here are implemented in **Cow**, an esoteric programming language where the only valid tokens are variations of "moo".

## What is Cow?

Cow is a Turing-complete esoteric language created in 2003. Every instruction is a case-insensitive variation of the word "moo":

| Instruction | Effect |
|-------------|--------|
| `moo` | Push 0 onto stack |
| `MOO` | Push 256 onto stack |
| `Moo` | Duplicate top of stack |
| `moO` | Rotate stack (move top to bottom) |
| `mOo` | Pop and discard |
| `OOO` | Input character |
| `MMM` | Output character |
| `OOM` | Pop and compare (jumps) |
| `oom` | Push stack size |
| `OOm` | Discard stack |

Everything else (including proper English) is ignored as comments.

## Running Cow Scripts

To run Cow scripts, you'll need a Cow interpreter:

```bash
# Download or use an online interpreter
# Python-based interpreter: https://github.com/joshkurz/Cow

python3 cow_interpreter.py uptime-monitor.cow
```

## Scripts in This Folder

- **uptime-monitor.cow** - Device uptime monitoring and group management (mostly moos)

## Why Cow?

Because sometimes you look at your code and think "this is absolutely mad", and Cow commits fully to that vision. Every single instruction is a variation of "MOO" - just like the confused state of actually implementing a production script in this language.

## Disclaimer

These are for entertainment purposes only. Your sanity and your team's productivity are worth more than whatever comedy value this achieves. Please use the Python or PowerShell versions for actual production work.
