# Setup Instructions

## Installation Steps

1. **Copy to ComfyUI**: Place this entire folder in your ComfyUI custom_nodes directory:
   ```
   ComfyUI/custom_nodes/comfy-lora-loader-with-triggerdb/
   ```

2. **Restart ComfyUI**: Completely restart ComfyUI to load the new node.

3. **Find the Node**: Look for "LoRa Loader with Trigger DB" in the "loaders" category when adding nodes.

## File Structure

```
comfy-lora-loader-with-triggerdb/
├── __init__.py                      # Node registration
├── lora_loader_with_triggerdb.py    # Main node implementation
├── web/
│   └── lora_loader_with_triggerdb.js # Frontend JavaScript
├── triggers_example.json            # Example triggers database
├── README.md                        # Documentation
└── SETUP.md                        # This file
```

## Usage Flow

1. **Add Node**: Add "LoRa Loader with Trigger DB" to your workflow
2. **Connect Model**: Connect your base model to the "model" input
3. **Select LoRa**: Choose a LoRa from the dropdown - trigger words will auto-load if available
4. **Edit Triggers**: Modify trigger words in the text field as needed
5. **Save**: Set "save_triggers" to True to save the trigger words to the database
6. **Connect Output**: Use the model output and optionally connect trigger words to prompt nodes

## Database Location

The `triggers.json` file will be created in your ComfyUI loras folder:
```
ComfyUI/models/loras/triggers.json
```

## Troubleshooting

- **Node doesn't appear**: Make sure you restarted ComfyUI after installation
- **Triggers don't save**: Check that ComfyUI has write permissions to the loras folder
- **JavaScript errors**: Check the browser console and ComfyUI terminal for error messages
- **LoRa not loading**: Verify the LoRa file exists in the correct location
