"""Regenerate the combined export/arity table for `PXD32D5-D4.md`.

Usage:
    $env:PYTHONPATH = "$env:TEMP\\caplib"
    python _pxd_rows.py            # write _pxd_rows.md and print the rows
    python _pxd_rows.py --splice   # also replace the table body in PXD32D5-D4.md

The table is generated from the same sweep as `_pxd_conventions.py`, so the
`Args` and `Evidence` columns can never drift from the disassembly; only the
`What the code does with the arguments` column is hand-written (the `notes`
dictionary below).  The `Ord` column comes from the export directory's ordinal
table - it is not the row number: this build numbers its exports alphabetically
(`ABilder` is ordinal 1, `W2P` is ordinal 96 while being the first export in
the image).  `--splice` rewrites the block between the
`<!--ARITY-ROWS:BEGIN-->` / `<!--ARITY-ROWS:END-->` markers in the master
document, which is why the master document must keep those two lines.
"""
import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "_pxd_conventions.py")).read().split("OFF = re.compile")[0])
OFF = re.compile(r'\[ebp ([+-]) (0x[0-9a-f]+|\d+)')

# Real export ordinals.  `named` maps an EAT index to its name and the EAT index
# is what the ordinal table stores, so the ordinal of a named export is
# `ordbase + EAT index`.  The name table is sorted alphabetically, therefore
# ordinals do NOT follow the address order: `ABilder` is ordinal 1 and `W2P` is
# ordinal 96, while `W2P` is the first export in the image.
ordinal_of = {name: ordbase + i for i, name in named.items()}

# In-image call sites, read by hand from `_pxd_dump.py <lo>-<hi>` or reported by
# `_pxd_xref.py`.  Prose rather than numbers, because that is what a reader needs.
xref = {
    'AInit': '1 internal caller pushes 1 dword',
    'AWaveDauer': '2 internal callers push 1 dword',
    'ADevice': '1 internal caller pushes 1 dword',
    'ARecStop': '4 internal callers push 0',
    'ARecTimer': '1 internal caller pushes 0',
    'AStop': '5 internal callers push 0',
    'AEnd': '1 internal caller pushes 0',
    'AStart': '1 internal caller pushes 1 dword',
    'APlay': 'internal caller pushes 12 dwords',
    'RWaveStop': '3 internal callers push 0',
    'RWaveParam': '2 internal callers push 2 dwords',
    'AMemory': '1 internal caller pushes 0',
    'ADSoff': '3 internal callers push 0',
    'RWaveLaden': '2 internal callers push 5 dwords',
    'DStart': '1 internal caller pushes 1 dword',
    'DCloseAll': '1 internal caller pushes 0',
    'DGetZeit': '3 internal callers push 1 dword',
    'DPlayFileClose': '2 internal callers push 1 dword',
    'RDrum': '1 internal caller pushes 3 dwords',
    'RWavToTemp': '1 internal caller pushes 7 dwords',
}

notes = {
'W2P': '2 dwords, both read: handed to the converter object at 0x100564E0 (setters 0x1000F55D / 0x1000F580 / 0x1000F59D, run 0x1000FB3E). Returns 1.',
'Extra': 'No arguments; builds the 8x8 1-bpp pattern bitmap from the bytes at 0x1004B2B0 and caches bitmap/brush in 0x100829EC / 0x100829F4, guarded by flag 0x10096CCC.',
'ANummer': 'No arguments; `mov eax, 0x01879487` - a constant outside the image, so a build/host tag rather than a pointer.',
'ExtraAus': 'No arguments; deletes the brush and the bitmap created by `Extra` (only when flag 0x10096CCC == 1).',
'AGetFree': '(char drive). Computes `arg + 0x41` = drive letter, builds "%c:\\", calls GetDriveTypeA + GetDiskFreeSpaceA. Returns free space in EDX:EAX.',
'AGetFull': '(char drive). Same drive-letter handling as `AGetFree`; total space, negative results clamped to 0x3E700000.',
'ASortOut': 'No arguments; pre-increments the word cursor at 0x1008E41C and returns `word [0x1009085E + n*2]` (table base 0x10090860 - 2, so the first call returns element 0).',
'ASortStart': 'No arguments; qsort (0x100323D4) over the word permutation array at 0x10090860 with comparator 0x10010B74.',
'ASortStart2': 'No arguments; the same qsort with the second comparator 0x10010BB6.',
'ASortInit': 'No arguments; zeroes the entry counter at 0x1008E41C.',
'ASortIn': '(char* name). Caps at 0x1900 (6400) entries; writes index n into `word [0x10090860 + n*2]` and lstrcpyA-copies the name into record n of the table pointed to by 0x100836F0, stride 0x80 (128 bytes). An empty or NULL name still consumes an index. Returns 0.',
'AMitte': '(int voice 0..0x30, int value 0..255). Classifies the value instead of storing it raw: 0x75..0x8B (117..139) writes 0, < 0xF writes 1, > 0xF0 writes 2, anything else is stored as the raw word. Target is voice+0x4A in the 0x84-stride array 0x10095108. Returns 1, or 0 for an out-of-range voice.',
'ATyp': '(int product type). Below 0x64 the value goes to 0x1008E358; 0x64..0xC7 sets word 0x10096D7C; 0xC8..0x12B sets word 0x10096D78. Returns 1.',
'AFenster': '(HWND). Stored at 0x1008E378; returns 1.',
'AInit': '(HWND). Stored at 0x1008E378, then sizes the voice array (0x84 * count at 0x10095108), the 0x124 and 0x2128 blocks, zeroes the 0x12B-dword block at 0x10082B1C, sets 0x10082B68 = 0x7FFF, builds the rate table at 0x100668F0, stores the doubles 1.0/2.0/3.0/4.0 (qwords at 0x10066968/0x10066970/0x10066978/0x10066980), sets the magic and starts the engine thread. Returns the int16 status.',
'AWaveDauer': '(char* path). CreateFileA, GetFileSize, ReadFile, CloseHandle; reads the header and derives the duration. Returns the duration dword.',
'BWaveDauer': '(handle, file offset, fallback). SetFilePointer + ReadFile of 0x10E (270) bytes, then parses the header: "RI" branch takes the length dword at +2 with a +/-1/7 tolerance window, "tP" branch takes a byte at +2 as a chunk skip. Mono (+0x14 word == 1) negates, the +0x16 word and an 8-bit format double it, rate 0x2B11 (44100) x4 and 0x5622 (22050) x2. Returns 0 on a non-WAV header.',
'ADevice': '1 dword declared but never read; probes waveOut devices and modes, stores the mode word at 0x1008BBE0 and a device id, zeroes the status word, returns 0.',
'ALautSet': '(int level). Stores the level at 0x10082AD8 and calls the mixer fader writer 0x10018B34 (speaker destination line, control type 0x50030001); when that fails it returns 0 without touching MME. Otherwise it maps the level through a `1.0 - level/10000` curve onto 0..0xFFFF, duplicates it into both channels and calls waveOutSetVolume on 0x100829E8 - opening the default waveOut device with the 44.1 kHz stereo 16-bit block at 0x10082AF0 first when 0x10083524 is -1. Returns 0.',
'ALautGet': '1 dword declared but never read; calls the mixer fader reader 0x10018DA6 (speaker destination line, control type 0x50030001), which returns the level normalised to 0..0x8000, and caches it in 0x10082AD8.',
'RGetName': '2 dwords declared, neither read: `mov eax,1; ret 8`. A stub in this build, unlike the 1998 build which copied a name here.',
'ARecTest': '(char* path). Copies the name to 0x10066810, opens the temp record file, sets up a 44.1 kHz stereo 16-bit WAVEHDR and calls waveInOpen twice (direct, then via `ADSoff`); the result code lands in 0x10096CF8 (0 = open failed, 1 = ok, 2 = busy). Returns it.',
'ARecDuplex': '1 dword declared but never read; sets the duplex flag 0x10096CFC = 1 and returns the int16 status.',
'ARecInit': '1 dword declared but never read; magic-guarded. Calls `ARecStop`, clears the record globals, opens waveIn, resets the queue, prepares and queues the 40-byte-stride buffer headers at 0x10083020. Returns the int16 status.',
'AGetString': '(char* dest, int selector). Copies one of the temp names (0x100823FC, 0x1008E64C, 0x100829F8, or a wsprintfA of "%spxd32p%c.tmp" into 0x10093AA8) into `dest`. Returns 0.',
'ARecStart': 'No arguments; magic-guarded. Clears two record counters, calls waveInStart, creates the record file (0x10096DF0) with a 0x2191C0-byte initial size and logs "Fehl beim Rec-Start" if that fails. Returns the int16 status.',
'ARecPlay': 'No arguments; magic-guarded. Calls `AWaveDauer(0x100823FC)`, i.e. it measures the temp record file rather than a live buffer; returns that duration, or the status word when the magic is missing.',
'ARecInput': '1 dword declared but never read: it is pushed to the internal mixer routine 0x100188EA and then ignored. That routine sets both channels of the waveIn destination fader (control type 0x50030001) to 0, i.e. it silences the record input. Returns 0.',
'ARecStop': 'No arguments; 323 instructions of teardown: waveInReset, waveInUnprepareHeader per buffer, closes the record file, clears the state words. Returns the int16 status.',
'ARecPegel': '(int selector). Selector 0 returns the live level at 0x10082600, otherwise the peak at 0x10066808. Returns the dword.',
'ARecTimer': 'No arguments; magic-guarded. Drains the finished waveIn buffers, calls WriteFile on them to the record file, re-prepares and re-queues them, and updates the peak at 0x10066808. Returns the int16 status.',
'AExport': '(char* name, char* text). Magic-guarded. Writes both strings into 0x10082224 and 0x10096BD8, opens the target with CreateFileA, runs the writer at 0x10013198 once before and once after `AStop`, and toggles 0x100823F8. Returns the int16 status.',
'AStop': 'No arguments; clears the ten transport globals, sets the request word 0x10096D88 = 1 and blocks in the wait loop at 0x100144C9. Returns 1.',
'Fade': 'No arguments; `mov eax,1; ret` - a 9-byte stub. The audio fade of the 1998 build is gone; nothing follows it here.',
'AEnd': 'No arguments; magic-guarded. Calls `AStop`, the thread-stop helper 0x100179FD, clears the state, deletes the four temp files through OpenFile(..., 0x200) and closes the mixer handle 0x100826BC.',
'ATimer': 'No arguments; `mov eax,1; ret`. The real pump is the internal routine at 0x10017255, immediately after the stub.',
'AGetTime': '(dword flag). Magic-free. Reads waveInGetPosition into a 4-byte TIME sample and/or calls `DGetZeit`, keeps four counters at 0x10096CE4..0x10096CF0, and returns the elapsed time scaled by 5. The argument selects the record branch.',
'ASetFader': '(dword unused, int level). Only the second argument is read: it is mapped from 10..30000 onto a signed attenuation (clamped to -0xF60) and pushed into DirectSound vtable +0x3C on 0x10093F50; a failure logs "Fader1" (0x1004B41C). Returns the HRESULT.',
'AStart': '(dword start position). Wrapper at 0x10017603: clears 0x10082BEC, sets the request word 0x10096D88 = 2, stores the position at 0x100829F0, blocks in 0x100144C9 and returns the status.',
'ASetPfad': '(char* prefix). lstrcpyA into 0x100835E0, then calls the internal restart at 0x10014233. Returns 0.',
'APlay': '12 dwords: sound number (word to event+0x10), name, name2 (either one replaces a NULL twin), three dwords stored at event+0xF4/+0xF8/+0xF0, a string copied to event+0x12, voice index (x0x84 into 0x10095108), start, duration, level, extra (event+0x104). Start/duration/level are masked &~3. Duration <= 0 writes the 0x6921CFF0 sentinel into event+4. Returns 0.',
'ABilder': '7 dwords, all stored: 0x1008BAB8, 0x1008BABC, 0x10082B0C, 0x1006680C, 0x100950FC, 0x1007A214, 0x10066800. Returns 0.',
'ABildpos': '1 dword declared but never read; returns the dword at 0x1008E354.',
'AExit': 'No arguments; sets the exit flag 0x100826C0 = 1 and signals the event at 0x10093A84 so the worker thread leaves its wait. Returns 1.',
'RWavePlay': 'No arguments; returns the int16 status word 0x10096DE0 - a stub in this build.',
'RWaveStop': 'No arguments; unmaps 0x100825F4, closes the two handles 0x100825F8 / 0x100825F0, clears 0x100825C0, Sleeps and re-runs the internal stop at 0x1001B0FF under lock 0x10082718. Returns the status.',
'RWaveParam': '(int index, dword value). Index 0x3C takes a separate path that ends at 0x10095184; every other index writes `value` to 0x10082B1C + index*4 (the 0x12B-dword parameter block). Returns the status.',
'RGetParam': '(int index). Returns `dword [0x10020020 + index*4]` - the getter that pairs with `RWaveParam`.',
'RWaveGetTime': 'No arguments; if 0x10083524 == -1 returns immediately, otherwise calls 0x100186EB and returns 0x10082954. Two counters are mixed, so this is an elapsed-time read.',
'RWaveSave': 'No arguments; `mov eax,1; ret` with a dummy `push ecx`. Stub.',
'RWaveFilter': '1 dword declared but never read; `mov eax,1; ret 4`. Stub.',
'RWaveTakt': 'No arguments; `mov eax,1; ret`. Stub.',
'AVbInfoCall': '1 dword declared but never read; `mov eax,1; ret 4`. The Visual Basic callback hook of the 1998 build is not wired up here.',
'RWaveGetInfo': '1 dword declared but never read; `xor eax,eax; ret 4`. Stub - returns 0.',
'RWaveSetInfo': '1 dword declared but never read; `mov eax,1; ret 4`. Stub.',
'RWaveRec': '1 dword declared but never read; returns the int16 status word - the file writer moved to `AExport`.',
'RMenu': 'No arguments; `mov eax,1; ret`. Stub - this build has no popup menu of its own.',
'RRecoSave': '1 dword declared but never read; if 0x1008B83C == 1 calls 0x1001865B, then returns the status.',
'RWavePause1': 'No arguments; walks voices 1..0x1C and calls DirectSound vtable +0x48 (Stop) on every active buffer, logging "Play0" (0x1004B440) on failure. Returns the status - this is the pause/stop half.',
'RWavePause2': 'No arguments; the mirror image of `RWavePause1`: same walk, vtable +0x30 (Play), error string "Play1" (0x1004B448). Returns the status - the resume half.',
'RTimer': 'No arguments; if 0x10096CC8 != 0 calls the internal tick at 0x10015666, then returns the status.',
'AMemory': 'No arguments; GlobalMemoryStatus into a 0x20-byte struct, sets the low-RAM word 0x10096D7A = 1 when total physical memory is between 0x3D0900 (4,000,000) and 0xF42400 (16,000,000). Returns the physical total.',
'ADSoff': 'No arguments; calls `DCloseAll` and returns 1 - "audio DirectSound off", used by `ARecTest` to give the device back before retrying waveInOpen. The mixer code that follows at 0x10018715 / 0x100188EA / 0x10018B34 / 0x10018DA6 belongs to separate internal functions, not to this export.',
'AGetInput': 'No arguments; a mixer read, not a waveIn enumeration. It fetches the waveIn destination line (MIXERLINE size 0xA8, component type 7), walks its sources, reads the fader control (type 0x50030001) and its per-channel values, averages the first and last channel and normalises min+max to 0..0x8000. Returns 1 when the mixer handle 0x100826BC is not open and 0x8000 when a mixer call fails.',
'ASelectMic': 'No arguments; `xor eax,eax` then a jump to the epilogue, so the entry always returns 0 without touching the mixer. The unreachable body at 0x100192B0 is the microphone source selector: it walks the waveIn line controls of class 0x70000000, matches item names against "Microphone" (0x1004B450) and "Micro" (0x1004B45C) and switches those items 1/0 - disabled in this build.',
'RWaveTransfer': '1 dword declared but never read; takes the lock 0x10082730 and calls the internal copy at 0x10018448. Returns the status.',
'AWelle': '(int x, int y, char* path). 117 instructions that open the file, build the min/max envelope and merge it into the display path. Returns 0.',
'AWellePos': '1 dword declared but never read; `xor eax,eax; ret 4`. Stub.',
'ALoad': '(char* path). Loads one of 200 (0xC8) sample slots at 0x10093B88: OpenFile + _hread, accepts magic 0x44445A53 ("SZDD", Microsoft LZ) and expands it through the LZ32 thunks at 0x10022E4C / 0x10022E46 / 0x10022E40, then CreateDIBSection + CreateCompatibleDC + SelectObject for the thumbnail. Returns 0 on success, the slot is 0x528 bytes.',
'AClose': '(int slot). Indexes 0x10093B88, calls DeleteDC on slot+0xF8 and DeleteObject on the DIB at slot+0xF4, frees the record and zeroes the slot. Returns 1.',
'ACloseAll': 'No arguments; runs the same teardown over all 200 slots and returns 1.',
'RWaveLaden': '(char* path, int mode, dword a3, dword a4, dword a5). Locks 0x10082718, unmaps the previous file, and unless mode == 0x7B calls `RWavToTemp(path, 0x1008E64C, 0, a3, a4, a5, 0)`; then CreateFileA + CreateFileMappingA + MapViewOfFile on 0x1008E64C, resets the 0x100825D0 mapping/display block and the 0x2760-byte buffer at 0x1008BBF0. Returns 1 on failure, 0 on success.',
'DStart': '(dword). Magic-free DirectSound bring-up: creates the device object with CoCreateInstance (CLSID 0x100434B0, IID 0x100434C0), sets the cooperative level and the 44.1 kHz primary format. Returns the HRESULT.',
'DCloseAll': 'No arguments; takes the lock 0x10082718, releases the primary buffer at 0x10093EB0 and the device at 0x10093ED8 through vtable +0x08, logs "Release Sound" (0x1004B4EC), clears the state word 0x10096D50 and returns 0.',
'ASetPitch': '(dword bias). For voices 1..0x1C writes `bias + 0x93A8` into slot+0x48 and, when the slot is active, calls DirectSound vtable +0x44 with it, logging "Pitch" (0x1004B560) on failure. Returns 1. The 0x93A8 (37,800) bias is unexplained [guess].',
'DGetZeit': '(dword). Advances the DirectSound clock at 0x10096CBC into 0x10093FAC, and when the device is open runs the internal update at 0x1001BF40 twice under lock 0x100950E0. Returns the time dword.',
'DPlayFileClose': '(int voice). Indexes the 0xA0-stride array at 0x10093F38: UnmapViewOfFile(slot+0x3C), CloseHandle(slot+0x40) and (slot+0x38), clears four fields. Returns 0/1.',
'DPlayFileCheck': '(int voice). Compares the mapped-file field slot+0x38 with 0, calls `DGetZeit` and compares the result against slot+0x44. Returns 0/1 - a "has this voice run out of mapped data" poll.',
'DPlayFile': '(char* path, dword a2, int voice). Opens the file, maps it (CreateFileA / GetFileSize / CreateFileMappingA / MapViewOfFile) and computes the 0x3B1-entry peak table at 0x1008F774 from timeGetTime for voices >= 0xA; then hands view, length and a2 to the voice'"'"'s DirectSound buffer via 0x1001BAE5 and 0x1001BD99. Returns 1.',
'DPlayUpdate': 'No arguments; skips out when the device is closed, the record word 0x100823F8 is 1 or the state word 0x10096CC8 is 0; otherwise closes every finished voice via `DPlayFileClose` and runs the internal mixer step 0x1001D74E under lock 0x10082718. Returns the step result.',
'APos': '(dword position). Stores into 0x1008BBD8 and returns 1.',
'ATest': '(dword, dword). Both arguments are ignored; `mov eax,1; ret 8`. Returns 1.',
'REffekt': '(char* command, int value). String-command dispatcher: lstrcmpiA against the table at 0x1004B620 ("GetPlayStatus", "CutOff", "EchoTime", "LoopMode", "PlayMatrix", "MetroStart", "StretchMode", "RecordAn", ...) and writes the effect globals 0x10082B6C-0x10082BA4 and 0x10090758-0x10090778. Returns the command result in EAX (0x10096CB4 / 0x10096CB8 for the two getters).',
'RDrum': '(char* command, int value, int extra). The drum half of the same dispatcher: "ADrum", "LDrum", "DrumPitch", "DrumPan", ... write 0x1009071C-0x1009076C, 0x1008E824-0x1008E830 and the 0x3B1-entry (945) peak table at 0x1008F774. Returns the result.',
'RpDrum': '(int, int, int). 11 instructions: pushes its three arguments unchanged and calls `RDrum` - a forwarding wrapper rather than a re-order, because both functions clean 0xc. Returns whatever `RDrum` returns.',
'RWavToTemp': '(char* in, char* out, int drive, dword, dword, dword, dword). The WAV reader/converter, 912 instructions. Caches the conversion by the triple 0x10096D24/0x10096D28/0x10096D2C; arg3 selects the temp drive through wsprintfA("%spxd32p%c.tmp", ..., arg3 + 0x63) at 0x1002071C. Returns the status.',
'ASetCur': '(int off). Cursor switch: when `off` is 0 it lazily LoadCursorA(0x7F8A) and SetCursor()s it (saving the previous cursor in 0x100826F4), otherwise it restores that cursor. Returns 1.',
'Debimem': '(char* tag). Dumps a debug line: GlobalMemoryStatus plus the seven counters in the struct, formatted with "%s ML:%ld TP:%ld AP:%ld TPa:%ld ..." (0x1004B9F8) and appended to c:\\memo.txt. Returns 1.',
'PInit': 'No arguments; convenience sequence `ADevice(0)`, `AInit(0)`, `RWaveParam(0x3C, 0x7D00)`. Returns 0.',
'PClose': 'No arguments; `AStop()` then `AEnd()`. Returns 0.',
'PStart': 'No arguments; `AStart(0xA80F570)` then `RWaveParam(0x32, 1)`. Returns 0.',
'PStop': 'No arguments; `AStop()`. Returns 0.',
'PPlay': '6 dwords; pushes five zeros and the literal "c" (0x1004B304) plus the six arguments into `APlay`, i.e. `APlay(0,0,0,0,0,"c",a1..a6)` - the single-character command form of the event call. Returns 0.',
'Stretcher': '(dword, dword, float ratio, dword). Compares the float ratio with the double 0.1 at 0x10043418; above it calls the object method 0x1000506E on 0x1008B8F0, otherwise 0x10005444, and returns the method result. 4 dwords, one of them a float.',
'ARegUnIn': '(char* uninstall string, char* display name). RegCreateKeyExA(HKLM, "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Dance eJay3", 0x1004BAA4), then RegSetValueExA "DisplayName" = arg2 and "UninstallString" = arg1, RegCloseKey. Returns 1.',
'ARegDelete': 'No arguments; RegDeleteKeyA(HKLM, 0x1004BB00) and returns 1.',
}


def main():
    lines = []
    missing = []
    for idx, (rva, name) in enumerate(exports):
        insns = sweep(rva)
        rets = [x for x in insns if x.mnemonic.startswith("ret")]
        sb = max([int(x.op_str, 0) for x in rets if x.op_str] or [0])
        pos = set()
        for ins in insns:
            for m in OFF.finditer(ins.op_str):
                if m.group(1) == "+":
                    pos.add(int(m.group(2), 0))
        n = sb // 4
        ev = 'ret %s' % ('0x%x' % sb if sb else '(none)')
        if pos:
            lo, hi = min(pos), max(pos)
            ev += '; reads [ebp+%#x]%s' % (lo, '' if lo == hi else '..[ebp+%#x]' % hi)
        else:
            ev += '; no frame argument read'
        if name in xref:
            ev += '; ' + xref[name]
        note = notes.get(name)
        if note is None:
            missing.append(name)
            note = ''
        lines.append('| %d | %d | `%s` | `0x%08X` | %d | %s | %s |' % (
            idx + 1, ordinal_of[name], name, imgbase + rva, n, ev, note))
    out = '\n'.join(lines) + '\n'
    open(os.path.join(HERE, "_pxd_rows.md"), "w", encoding="utf-8", newline="\n").write(out)
    print(out)
    if missing:
        print("MISSING NOTES: %s" % ", ".join(missing))
    if "--splice" in sys.argv:
        splice(out)
        print("spliced into PXD32D5-D4.md")


def splice(rows):
    """Replace the block between the ARITY-ROWS markers in the master document."""
    path = os.path.join(HERE, "PXD32D5-D4.md")
    text = open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    begin = "<!--ARITY-ROWS:BEGIN-->"
    end = "<!--ARITY-ROWS:END-->"
    i, j = text.index(begin) + len(begin), text.index(end)
    text = text[:i] + "\n" + rows + text[j:]
    open(path, "w", encoding="utf-8", newline="\n").write(text)


main()
