# Agent Notes

## Encoding Checks

- When checking for Chinese text corruption, first read the file explicitly as UTF-8.
- Do not treat terminal or PowerShell display mojibake as source corruption by itself.
- Only report text as corrupted when it still appears corrupted after a UTF-8 read of the file contents.
