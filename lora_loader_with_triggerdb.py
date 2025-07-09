import os
import json
import folder_paths
import comfy.sd
import comfy.utils
from aiohttp import web
import server


class LoRaLoaderWithTriggerDB:
    def __init__(self):
        self.lora_path = folder_paths.get_folder_paths("loras")[0] if folder_paths.get_folder_paths("loras") else ""
        self.triggers_file = os.path.join(self.lora_path, "triggers.json")
    
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
            }
        }
    
    RETURN_TYPES = ("MODEL", "STRING", "STRING")
    RETURN_NAMES = ("model", "all_triggers", "active_triggers")
    FUNCTION = "load_lora"
    CATEGORY = "loaders"
    
    def load_triggers_db(self):
        """Load the triggers database from JSON file"""
        if os.path.exists(self.triggers_file):
            try:
                with open(self.triggers_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading triggers.json: {e}")
                return {}
        return {}
    
    def save_triggers_db(self, triggers_db):
        """Save the triggers database to JSON file"""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.triggers_file), exist_ok=True)
            
            with open(self.triggers_file, 'w', encoding='utf-8') as f:
                json.dump(triggers_db, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving triggers.json: {e}")
    
    def get_lora_base_name(self, lora_name):
        """Get the base name of the LoRa file (without extension)"""
        return os.path.splitext(lora_name)[0]
    
    def load_lora(self, model, lora_name, strength_model, all_triggers, active_triggers):
        if strength_model == 0:
            return (model, all_triggers, active_triggers)
        
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
        
        # Get LoRa path and triggers file
        lora_path = folder_paths.get_folder_paths("loras")[0] if folder_paths.get_folder_paths("loras") else ""
        triggers_file = os.path.join(lora_path, "triggers.json")
        
        # Load triggers database
        triggers_db = {}
        if os.path.exists(triggers_file):
            try:
                with open(triggers_file, 'r', encoding='utf-8') as f:
                    triggers_db = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading triggers.json: {e}")
        
        # Get base name and lookup triggers
        lora_base_name = os.path.splitext(lora_name)[0]
        lora_data = triggers_db.get(lora_base_name, {})
        
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
        
        # Get LoRa path and triggers file
        lora_path = folder_paths.get_folder_paths("loras")[0] if folder_paths.get_folder_paths("loras") else ""
        triggers_file = os.path.join(lora_path, "triggers.json")
        
        # Load existing triggers database
        triggers_db = {}
        if os.path.exists(triggers_file):
            try:
                with open(triggers_file, 'r', encoding='utf-8') as f:
                    triggers_db = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading triggers.json: {e}")
        
        # Save trigger words
        lora_base_name = os.path.splitext(lora_name)[0]
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


# JavaScript to handle dynamic trigger loading will be in web/lora_loader_with_triggerdb.js


NODE_CLASS_MAPPINGS = {
    "LoRaLoaderWithTriggerDB": LoRaLoaderWithTriggerDB
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoRaLoaderWithTriggerDB": "LoRa Loader with Trigger DB"
}