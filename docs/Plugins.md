# Plugins

`tgcf` leverages a modular plugin system to inspect, block, or mutate messages mid-flight.

## Official Plugins

1. **Filter**: Whitelist or blacklist messages based on logic, users, or text.
2. **Format**: Apply bold, italics, or code formatting.
3. **Replace**: Regex-based search and replace.
4. **Watermark**: Stamp images and videos (Requires system `ffmpeg` package).
5. **OCR**: Optical character recognition for image text extraction (Requires system `tesseract-ocr` package).

---

## Replace Plugin Reference

The replace plugin parses input as YAML key-value pairs (`original: replacement`). It supports strict string matching and Regular Expressions.

### Basic Removal
Replace text with an empty string to strip it completely from messages.
```yaml
"evil_text": ""
```

### Regular Expressions
If regex features are enabled in the plugin settings, you can perform advanced matching (e.g., stripping URLs):
```yaml
'(@|www|https?)\S+': ''
```
*Tip: Use single quotes to encapsulate regex strings to prevent YAML parsing errors with special characters.*

### Text Formatting 
You can dynamically format specific matching text using special Telegram syntax keywords:
```yaml
# Makes all instances of 'hello' bold
"(hello)": bold
```

Alternatively, use standard markdown wrappers in the replacement value:
```yaml
# Converts 'python' to bolded 'javascript'
"(python)": "**javascript**"
```

Supported format wrappers:
- `bold`: `**`
- `italics`: `__`
- `code`: `` ` ``
- `strike`: `~~`
