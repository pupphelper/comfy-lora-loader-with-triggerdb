import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Extension for LoRa Loader with Trigger DB
app.registerExtension({
    name: "LoRaLoaderWithTriggerDB",
    
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "LoRaLoaderWithTriggerDB") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            
            nodeType.prototype.onNodeCreated = function() {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                
                // Find the lora_name widget and trigger_words widget
                const loraWidget = this.widgets.find(w => w.name === "lora_name");
                const triggerWidget = this.widgets.find(w => w.name === "trigger_words");
                
                if (loraWidget && triggerWidget) {
                    // Store original callback
                    const originalCallback = loraWidget.callback;
                    
                    // Override the callback to load triggers when LoRa changes
                    loraWidget.callback = async function(value) {
                        if (originalCallback) {
                            originalCallback.call(this, value);
                        }
                        
                        // Load triggers for the selected LoRa
                        try {
                            const response = await api.fetchApi("/lora_triggers", {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json",
                                },
                                body: JSON.stringify({
                                    lora_name: value
                                })
                            });
                            
                            if (response.ok) {
                                const data = await response.json();
                                if (data.trigger_words) {
                                    triggerWidget.value = data.trigger_words;
                                    // Trigger update to reflect the change
                                    triggerWidget.callback && triggerWidget.callback(data.trigger_words);
                                }
                            }
                        } catch (error) {
                            console.log("Could not load triggers:", error);
                        }
                    };
                }
                
                return r;
            };
        }
    }
});

// Register API endpoint for loading triggers
app.registerExtension({
    name: "LoRaLoaderWithTriggerDB.API",
    
    async setup() {
        // This will be handled by the Python backend
        // We just need to ensure the API endpoint exists
    }
});
