# cpu_thermals

A small Linux CLI utility that displays live CPU package temperatures with color-coded readings and ASCII bar graphs. Supports both Intel (`coretemp`) and AMD (`k10temp`) sensors via `lm-sensors`.

## Features

- Live, refreshing temperature readout for up to two CPU packages
- Color-coded output: green (< 80 °C), yellow (80–90 °C), red (≥ 90 °C)
- ASCII bar graph scaled from 40 °C to 100 °C
- Auto-detects Intel `Package id` and AMD `Tctl` readings from `sensors` output
- Configurable refresh interval

## Requirements

- Linux with `lm-sensors` installed and configured (`sensors-detect` should have been run)
- Python 3 (standard library only — no extra dependencies)
- A terminal with ANSI color support

Install `lm-sensors` on Debian/Ubuntu:

```bash
sudo apt install lm-sensors
sudo sensors-detect
```

## Usage

```bash
./cpu_thermals.py            # default 2-second refresh
./cpu_thermals.py 1          # refresh every 1 second
./cpu_thermals.py 0.5        # refresh every 0.5 seconds
```

Press `Ctrl-C` to exit.

## Example output

```
TIME       | CPU0        | CPU1        | CPU0 BAR (40-100C)   | CPU1 BAR (40-100C)
-------------------------------------------------------------------------------------
10:26:14   |  62.0°C     |  64.0°C     | ███████-------------  | ███████-------------
```

## Notes

- The script always reports two values; if only one CPU package is detected, the second column is padded with `0.0°C`.
- If `sensors` is not installed or fails to run, the script exits with an error.

## License

MIT
