# EF-2000 Typhoon for Nuclear Option

Turns the FS-12 Revoker into a Eurofighter Typhoon: a complete new exterior and a fully modelled, working cockpit.
Flight performance, weapons and damage are the Revoker's own, unchanged.

**Download:** see the [Releases](../../releases) page. Download both zips of the latest release and unzip both into
the game folder (the one with `NuclearOption.exe`). Needs BepInEx 5 (x64).

- 401,938 triangles in 166 parts (cockpit 248,288, exterior 153,650)
- Over 80 texture maps, up to 8192 x 8192
- 26 moving parts linked to the game's controls and systems
- 7 working cockpit displays, 89 lit legends that follow the aircraft's state
- `[` and `]` step the left and right displays through their pages

## Source available

This repository holds the source of the plugin (`src`, C#) and the scripts that build the model and its textures
(`model`, `dev/tools`). It is published so you can read it and see how the mod works.

**Please ask before changing or redistributing it.** The plugin, its source, the scripts and the data files are
the author's own work: changing them, publishing changed versions or re-uploading them needs permission first.
Open an issue and say what you want to do. See [LICENSE.txt](LICENSE.txt).

The aircraft model and its textures (in the release zips) are adapted from
["Eurofighter Typhoon - Fighter Jet - Free" by bohmerang](https://sketchfab.com/3d-models/eurofighter-typhoon-fighter-jet-free-992bcc8987964ca09d55410330aa8579)
and are shared under the same licence, CC BY-NC-SA 4.0: free to share and adapt with credit, non-commercial only.
See [CREDITS.txt](CREDITS.txt).

## Building the plugin

Copy `Directory.Build.props.example` to `Directory.Build.props`, set your game path in it, then
`dotnet build -c Release`. For the release build without settings add `-p:DefineConstants=PRODUCTION`.

The model scripts need source files that are not in this repository (the original model and working inputs),
so they are here to read, not to run as they are.

Not affiliated with Shockfront Studios or Eurofighter GmbH.
