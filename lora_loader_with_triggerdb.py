import os
import json
import re
import folder_paths
import comfy.sd
import comfy.utils
from aiohttp import web
import server

def get_user_db_path():
    """Get the user database directory"""
    try:
        # Get the ComfyUI root directory
        comfy_path = folder_paths.base_path
        user_db_path = os.path.join(comfy_path, "user", "default", "user-db")
        os.makedirs(user_db_path, exist_ok=True)
        return user_db_path
    except Exception as e:
        print(f"Error determining user DB path: {e}")
        # Fallback to the old location
        lora_path = folder_paths.get_folder_paths("loras")[0] if folder_paths.get_folder_paths("loras") else ""
        return lora_path


def extract_triggers_from_metadata(meta):
    """Extract trigger words from LoRa metadata"""
    if not isinstance(meta, dict):
        return []
    
    # Try common keys used by Kohya and others
    for key in ["ss_tag_frequency", "ss_tag_strings", "trained_words", "trigger_words"]:
        if key in meta:
            val = meta[key]
            if isinstance(val, str):
                # Sometimes it's a JSON string or comma-separated
                try:
                    val = json.loads(val)
                except Exception:
                    val = [v.strip() for v in val.split(",")]
            if isinstance(val, dict):
                # Kohya's ss_tag_frequency is a dict of word:count
                return list(val.keys())
            if isinstance(val, list):
                return [str(v) for v in val]
    
    # Try to find any key with "trigger" or "word" in it
    for k, v in meta.items():
        if "trigger" in k or "word" in k:
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = [vv.strip() for vv in v.split(",")]
            if isinstance(v, dict):
                return list(v.keys())
            if isinstance(v, list):
                return [str(x) for x in v]
    return []

def clean_trigger_word(word):
    """Clean trigger word by removing leading numbers and underscores"""
    # Remove leading numbers and underscores, e.g. '1_girl' -> 'girl'
    cleaned = re.sub(r'^\d+_', '', word)
    if cleaned.lower() in {"img", "img_dir", "image_dir"}:
        return None  # Filter out these words
    return cleaned

def read_lora_metadata(lora_path):
    """Read metadata from LoRa file"""
    if not os.path.isfile(lora_path):
        return {}
    
    ext = os.path.splitext(lora_path)[1].lower()
    meta = {}
    
    try:
        if ext == ".safetensors":
            # Read safetensors metadata
            try:
                from safetensors.torch import safe_open
                with safe_open(lora_path, framework="pt", device="cpu") as f:
                    meta = f.metadata()
            except ImportError:
                # Fallback: try to use ComfyUI's built-in loading method
                try:
                    import safetensors
                    with safetensors.safe_open(lora_path, framework="pt", device="cpu") as f:
                        meta = f.metadata()
                except ImportError:
                    print("safetensors not available, cannot read .safetensors metadata")
                    return {}
            except Exception as e:
                print(f"Error reading safetensors metadata from {lora_path}: {e}")
                return {}
        elif ext in [".pt", ".bin"]:
            # Read PyTorch metadata
            try:
                import torch
                data = torch.load(lora_path, map_location="cpu")
                if "metadata" in data:
                    meta = data["metadata"]
                elif "meta" in data:
                    meta = data["meta"]
                else:
                    # Sometimes the dict itself contains metadata
                    meta = data
            except Exception as e:
                print(f"Error reading torch metadata from {lora_path}: {e}")
                return {}
        else:
            print(f"Unsupported file type: {ext}")
            return {}
    except Exception as e:
        print(f"Error reading metadata from {lora_path}: {e}")
        return {}
    
    return meta


class LoRaLoaderWithTriggerDB:
    def __init__(self):
        self.user_db_path = get_user_db_path()
        self.triggers_file = os.path.join(self.user_db_path, "lora-triggers.json")
    
    @classmethod
    def INPUT_TYPES(cls):
        # Get list of LoRa files
        loras = folder_paths.get_filename_list("loras")
        
        return {
            "required": {
                "model": ("MODEL",),
                "lora_name": (loras, {"default": loras[0] if loras else ""}),
                "strength_model": ("FLOAT", {"default": 1.0, "min": -20.0, "max": 20.0, "step": 0.01}),
                "all_triggers": ("STRING", {"multiline": True, "default": "", "dynamicPrompts": False}),
                "active_triggers": ("STRING", {"multiline": True, "default": "", "dynamicPrompts": False}),
                "autoload_triggers": ("BOOLEAN", {"default": True}),  # <-- NEW TOGGLE
            }
        }
    
    RETURN_TYPES = ("MODEL", "STRING", "STRING")
    RETURN_NAMES = ("model", "all_triggers", "active_triggers")
    FUNCTION = "load_lora"
    CATEGORY = "loaders"
    
    def get_lora_base_name(self, lora_name):
        """Get the base name of the LoRa file (without extension), normalized for cross-platform compatibility"""
        # Normalize path separators to forward slashes for cross-platform compatibility
        normalized_name = lora_name.replace("\\", "/")
        return os.path.splitext(normalized_name)[0]
    
    def normalize_lora_key(self, lora_name):
        """Normalize LoRa name for cross-platform database key matching"""
        return lora_name.replace("\\", "/")
    
    def find_lora_in_db(self, triggers_db, lora_name):
        """Find LoRa data in database with cross-platform path matching"""
        # Get the normalized current key
        current_key = self.get_lora_base_name(lora_name)
        
        # First try exact match (fastest)
        if current_key in triggers_db:
            return triggers_db[current_key]
        
        # If no exact match, try cross-platform matching
        # Normalize current key for comparison
        current_normalized = current_key.replace("\\", "/")
        
        # Check all existing keys with normalization
        for stored_key, stored_data in triggers_db.items():
            stored_normalized = stored_key.replace("\\", "/")
            if stored_normalized == current_normalized:
                return stored_data
        
        # No match found
        return {}
    
    def load_lora(self, model, lora_name, strength_model, all_triggers, active_triggers, autoload_triggers):
        if strength_model == 0:
            return (model, all_triggers, active_triggers)

        if autoload_triggers:
            # --- Auto-load triggers based on lora_name ---
            triggers_db = {}
            if os.path.exists(self.triggers_file):
                try:
                    with open(self.triggers_file, 'r', encoding='utf-8') as f:
                        triggers_db = json.load(f)
                except (json.JSONDecodeError, Exception) as e:
                    print(f"Error loading triggers.json: {e}")

            lora_data = self.find_lora_in_db(triggers_db, lora_name)
            if isinstance(lora_data, str):
                all_triggers = lora_data
                active_triggers = lora_data
            elif isinstance(lora_data, dict) and lora_data:
                all_triggers = lora_data.get("all_triggers", "")
                active_triggers = lora_data.get("active_triggers", "") or all_triggers
            else:
                # Fallback: Try to load from metadata
                lora_path = folder_paths.get_full_path("loras", lora_name)
                meta = read_lora_metadata(lora_path)
                triggers = extract_triggers_from_metadata(meta)
                cleaned_triggers = []
                for trigger in triggers:
                    cleaned = clean_trigger_word(trigger)
                    if cleaned and cleaned not in cleaned_triggers:
                        cleaned_triggers.append(cleaned)
                all_triggers = ", ".join(cleaned_triggers)
                active_triggers = all_triggers
            # --- END AUTOLOAD ---

        # Load LoRa
        lora_path = folder_paths.get_full_path("loras", lora_name)
        lora = None
        if os.path.isfile(lora_path):
            lora = comfy.utils.load_torch_file(lora_path, safe_load=True)

        if lora is None:
            print(f"Failed to load LoRa: {lora_name}")
            return (model, all_triggers, active_triggers)

        # Apply LoRa to model only
        model_lora, _ = comfy.sd.load_lora_for_models(model, None, lora, strength_model, 0)

        # Return model with LoRa applied and current trigger words
        return (model_lora, all_triggers, active_triggers)


# API endpoint for loading triggers
@server.PromptServer.instance.routes.post("/lora_triggers")
async def load_lora_triggers(request):
    try:
        data = await request.json()
        lora_name = data.get("lora_name", "")
        
        if not lora_name:
            return web.json_response({"all_triggers": "", "active_triggers": ""})
        
        # Get user database directory and triggers file
        user_db_path = get_user_db_path()
        triggers_file = os.path.join(user_db_path, "lora-triggers.json")
        
        # Load triggers database
        triggers_db = {}
        if os.path.exists(triggers_file):
            try:
                with open(triggers_file, 'r', encoding='utf-8') as f:
                    triggers_db = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading triggers.json: {e}")
        
        # Get base name and lookup triggers with cross-platform matching
        instance = LoRaLoaderWithTriggerDB()
        lora_data = instance.find_lora_in_db(triggers_db, lora_name)
        
        # Handle both old format (string) and new format (dict)
        if isinstance(lora_data, str):
            # Old format - migrate to new format
            all_triggers = lora_data
            active_triggers = ""
        else:
            # New format
            all_triggers = lora_data.get("all_triggers", "")
            active_triggers = lora_data.get("active_triggers", "")
        
        return web.json_response({"all_triggers": all_triggers, "active_triggers": active_triggers})
        
    except Exception as e:
        print(f"Error in load_lora_triggers: {e}")
        return web.json_response({"all_triggers": "", "active_triggers": ""}, status=500)


# API endpoint for saving triggers
@server.PromptServer.instance.routes.post("/lora_triggers_save")
async def save_lora_triggers(request):
    try:
        data = await request.json()
        lora_name = data.get("lora_name", "")
        all_triggers = data.get("all_triggers", "")
        active_triggers = data.get("active_triggers", "")
        
        if not lora_name:
            return web.json_response({"success": False, "message": "No LoRa name provided"})
        
        # Get user database directory and triggers file
        user_db_path = get_user_db_path()
        triggers_file = os.path.join(user_db_path, "lora-triggers.json")
        
        # Load existing triggers database
        triggers_db = {}
        if os.path.exists(triggers_file):
            try:
                with open(triggers_file, 'r', encoding='utf-8') as f:
                    triggers_db = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading triggers.json: {e}")
        
        # Save trigger words with normalized path
        instance = LoRaLoaderWithTriggerDB()
        lora_base_name = instance.get_lora_base_name(lora_name)  # This normalizes the path
        
        if all_triggers.strip() or active_triggers.strip():
            triggers_db[lora_base_name] = {
                "all_triggers": all_triggers.strip(),
                "active_triggers": active_triggers.strip()
            }
            
            # Save to file
            try:
                os.makedirs(os.path.dirname(triggers_file), exist_ok=True)
                with open(triggers_file, 'w', encoding='utf-8') as f:
                    json.dump(triggers_db, f, indent=2, ensure_ascii=False)
                
                print(f"Saved triggers for {lora_base_name}: all='{all_triggers}', active='{active_triggers}'")
                return web.json_response({"success": True, "message": f"Saved triggers for {lora_base_name}"})
                
            except Exception as e:
                print(f"Error saving triggers.json: {e}")
                return web.json_response({"success": False, "message": f"Error saving: {e}"})
        else:
            return web.json_response({"success": False, "message": "No trigger words to save"})
        
    except Exception as e:
        print(f"Error in save_lora_triggers: {e}")
        return web.json_response({"success": False, "message": f"Error: {e}"}, status=500)


# API endpoint for loading metadata
@server.PromptServer.instance.routes.post("/lora_metadata")
async def load_lora_metadata(request):
    try:
        data = await request.json()
        lora_name = data.get("lora_name", "")
        
        if not lora_name:
            return web.json_response({"success": False, "message": "No LoRa name provided"})
        
        # Get full path to LoRa file
        lora_path = folder_paths.get_full_path("loras", lora_name)
        
        if not os.path.isfile(lora_path):
            return web.json_response({"success": False, "message": f"LoRa file not found: {lora_name}"})
        
        # Read metadata from LoRa file
        meta = read_lora_metadata(lora_path)
        
        if not meta:
            return web.json_response({"success": False, "message": "No metadata found in LoRa file"})
        
        # Extract trigger words from metadata
        triggers = extract_triggers_from_metadata(meta)
        
        if not triggers:
            return web.json_response({"success": False, "message": "No trigger words found in metadata"})
        
        # Clean trigger words
        cleaned_triggers = []
        for trigger in triggers:
            cleaned = clean_trigger_word(trigger)
            if cleaned and cleaned not in cleaned_triggers:  # Remove duplicates and None values
                cleaned_triggers.append(cleaned)
        
        if not cleaned_triggers:
            return web.json_response({"success": False, "message": "No valid trigger words found after cleaning"})
        
        # Join triggers with commas
        all_triggers = ", ".join(cleaned_triggers)
        
        # For active triggers, use the same as all triggers initially
        active_triggers = all_triggers
        
        return web.json_response({
            "success": True,
            "all_triggers": all_triggers,
            "active_triggers": active_triggers,
            "message": f"Loaded {len(cleaned_triggers)} trigger words from metadata"
        })
        
    except Exception as e:
        print(f"Error in load_lora_metadata: {e}")
        return web.json_response({"success": False, "message": f"Error loading metadata: {e}"}, status=500)


NODE_CLASS_MAPPINGS = {
    "LoRaLoaderWithTriggerDB": LoRaLoaderWithTriggerDB
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoRaLoaderWithTriggerDB": "LoRa Loader with Trigger DB"
}