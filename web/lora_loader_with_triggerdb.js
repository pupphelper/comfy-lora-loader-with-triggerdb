import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

console.log("LoRa Loader JavaScript file loaded!");

// Extension for LoRa Loader with Trigger DB
app.registerExtension({
    name: "LoRaLoaderWithTriggerDB",
    
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        console.log("beforeRegisterNodeDef called for:", nodeData.name);
        
        if (nodeData.name === "LoRaLoaderWithTriggerDB") {
            console.log("Registering LoRa Loader with Trigger DB");
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            
            nodeType.prototype.onNodeCreated = function() {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                
                console.log("LoRa Loader Node Created - widgets:", this.widgets.map(w => w.name));
                
                // Find the widgets
                const loraWidget = this.widgets.find(w => w.name === "lora_name");
                const allTriggersWidget = this.widgets.find(w => w.name === "all_triggers");
                const activeTriggersWidget = this.widgets.find(w => w.name === "active_triggers");
                
                console.log("Found widgets:", { 
                    lora: !!loraWidget, 
                    allTriggers: !!allTriggersWidget, 
                    activeTriggers: !!activeTriggersWidget 
                });
                
                if (loraWidget && allTriggersWidget && activeTriggersWidget) {
                    console.log("Adding buttons to LoRa Loader node");
                    
                    // Alternative approach: Use change event instead of overriding callback
                    // This preserves the original filtering behavior completely
                    if (loraWidget.inputEl) {
                        loraWidget.inputEl.addEventListener('change', async (event) => {
                            const value = event.target.value;
                            
                            // Only auto-load triggers if both trigger fields are empty
                            if (value && 
                                (!allTriggersWidget.value || allTriggersWidget.value.trim() === "") &&
                                (!activeTriggersWidget.value || activeTriggersWidget.value.trim() === "")) {
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
                                        if (data.all_triggers) {
                                            allTriggersWidget.value = data.all_triggers;
                                            allTriggersWidget.callback && allTriggersWidget.callback(data.all_triggers);
                                        }
                                        if (data.active_triggers) {
                                            activeTriggersWidget.value = data.active_triggers;
                                            activeTriggersWidget.callback && activeTriggersWidget.callback(data.active_triggers);
                                        }
                                    }
                                } catch (error) {
                                    console.log("Could not auto-load triggers:", error);
                                }
                            }
                        });
                    }
                    
                    // Keep the original callback approach as backup
                    // Store original callback
                    const originalLoraCallback = loraWidget.callback;
                    
                    // Override the LoRa callback to auto-load triggers when LoRa changes
                    // But preserve the original filtering functionality
                    loraWidget.callback = async function(value) {
                        // Call the original callback first to preserve filtering behavior
                        if (originalLoraCallback) {
                            const result = originalLoraCallback.call(this, value);
                            // If the original callback returns something, respect it
                            if (result !== undefined) {
                                return result;
                            }
                        }
                        
                        // Only auto-load triggers if this looks like a complete LoRa selection
                        // (not just typing for filtering)
                        if (value && 
                            (!allTriggersWidget.value || allTriggersWidget.value.trim() === "") &&
                            (!activeTriggersWidget.value || activeTriggersWidget.value.trim() === "")) {
                            // Add a small delay to ensure this is a final selection, not just typing
                            setTimeout(async () => {
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
                                        if (data.all_triggers) {
                                            allTriggersWidget.value = data.all_triggers;
                                            allTriggersWidget.callback && allTriggersWidget.callback(data.all_triggers);
                                        }
                                        if (data.active_triggers) {
                                            activeTriggersWidget.value = data.active_triggers;
                                            activeTriggersWidget.callback && activeTriggersWidget.callback(data.active_triggers);
                                        }
                                    }
                                } catch (error) {
                                    console.log("Could not auto-load triggers:", error);
                                }
                            }, 500); // 500ms delay to avoid triggering during typing
                        }
                    };
                    
                    // Add load triggers button
                    console.log("Adding load triggers button");
                    this.addWidget("button", "📥 Load Triggers", "", async () => {
                        const loraName = loraWidget.value;
                        if (!loraName) {
                            console.log("No LoRa selected");
                            return;
                        }
                        
                        try {
                            const response = await api.fetchApi("/lora_triggers", {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json",
                                },
                                body: JSON.stringify({
                                    lora_name: loraName
                                })
                            });
                            
                            if (response.ok) {
                                const data = await response.json();
                                if (data.all_triggers || data.active_triggers) {
                                    if (data.all_triggers) {
                                        allTriggersWidget.value = data.all_triggers;
                                        allTriggersWidget.callback && allTriggersWidget.callback(data.all_triggers);
                                    }
                                    if (data.active_triggers) {
                                        activeTriggersWidget.value = data.active_triggers;
                                        activeTriggersWidget.callback && activeTriggersWidget.callback(data.active_triggers);
                                    }
                                    console.log(`Loaded triggers for ${loraName}: all="${data.all_triggers}", active="${data.active_triggers}"`);
                                } else {
                                    console.log(`No saved triggers found for ${loraName}`);
                                }
                            }
                        } catch (error) {
                            console.error("Error loading triggers:", error);
                        }
                    }, { serialize: false });
                    
                    // Add save triggers button
                    this.addWidget("button", "💾 Save Triggers", "", async () => {
                        const loraName = loraWidget.value;
                        const allTriggers = allTriggersWidget.value;
                        const activeTriggers = activeTriggersWidget.value;
                        
                        if (!loraName) {
                            console.log("No LoRa selected");
                            return;
                        }
                        
                        if ((!allTriggers || allTriggers.trim() === "") && 
                            (!activeTriggers || activeTriggers.trim() === "")) {
                            console.log("No trigger words to save");
                            return;
                        }
                        
                        try {
                            const response = await api.fetchApi("/lora_triggers_save", {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json",
                                },
                                body: JSON.stringify({
                                    lora_name: loraName,
                                    all_triggers: allTriggers,
                                    active_triggers: activeTriggers
                                })
                            });
                            
                            if (response.ok) {
                                const data = await response.json();
                                if (data.success) {
                                    console.log(data.message);
                                } else {
                                    console.error("Save failed:", data.message);
                                }
                            }
                        } catch (error) {
                            console.error("Error saving triggers:", error);
                        }
                    }, { serialize: false });
                    
                    console.log("Finished adding buttons. Total widgets:", this.widgets.length);
                    this.widgets.forEach((w, i) => console.log(`Widget ${i}: ${w.name} (${w.type})`));
                    
                    // Force the node to resize to show the new buttons
                    this.computeSize();
                    this.setDirtyCanvas(true, true);
                } else {
                    console.log("Could not find required widgets");
                }
                
                return r;
            };
        }
    }
});
