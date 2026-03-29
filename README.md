# Cum# Editor

Cum# Editor is a lightweight desktop code editor for the custom **Cum#** language.
It opens and saves `.cum` files, highlights Cum# syntax, shows line numbers,
tracks unsaved changes, and includes a project sidebar for opening folders.

## Cum# language sketch

This project treats **Cum#** as a simple, C-style language with these conventions:

- file extension: `.cum`
- line comments: `// like this`
- block comments: `/* like this */`
- functions: `fn name(arg: Type) -> Type { ... }`
- variables: `let` and `mut`
- flow control: `if`, `else`, `while`, `for`, `loop`, `match`, `case`
- async features: `async`, `await`, `spawn`
- literals: strings, numbers, `true`, `false`, `null`

The editor only provides language-aware editing. It does not include a Cum# compiler or runtime.

## Features

- multi-tab editor
- open/save/save-as for `.cum` and other source files
- custom Cum# syntax highlighting
- line numbers and current-line highlight
- project tree sidebar
- starter template for new Cum# files
- desktop launcher metadata for DebianMOSS `mosspkg`

## Install with mosspkg

### Local path install

```bash
mosspkg install /full/path/to/cumsharp-editor
```

### GitHub install

```bash
mosspkg install https://github.com/YOURNAME/cumsharp-editor
```

`mosspkg` will detect the Python project from `pyproject.toml`, install it with
`pipx` or `pip --user`, and create a launcher from `mossapp.json`.

## Run

```bash
cumsharp-editor
```

## Example Cum# file

See `examples/hello.cum`.

## Notes for DebianMOSS

This project is designed around the current DebianMOSS source-install workflow,
where `mosspkg` is used for user-local community apps. If you later want to ship
it inside the ISO, place the built launcher or wrapper into
`config/includes.chroot/usr/local/bin/` and add a desktop entry under
`config/includes.chroot/usr/share/applications/` before rebuilding the image.


## Publish from Windows

A PowerShell helper is included at:

```powershell
scripts/publish.ps1
```

It is preconfigured to push this project to:

- `https://github.com/masi621/cumsharp.git`
- branch `main`

The helper is also added to `.gitignore`, so it stays local by default.

Typical Windows PowerShell usage:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\publish.ps1
```

Requirements:

- Git for Windows installed
- you are already authenticated to GitHub in Git
