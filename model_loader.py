import torch
import torch.nn as nn
import torchvision.models as models

device = torch.device("cpu")  # Force CPU explicitly

# ─── BRAIN MODEL ───────────────────────────────────────────────────────────────
brain_model = models.resnet18(weights=None)
brain_model.fc = nn.Linear(brain_model.fc.in_features, 4)
brain_model.load_state_dict(torch.load(
    "models/brain_model.pth", map_location="cpu"
))
brain_model = brain_model.to(device)
brain_model.eval()
brain_classes = ["glioma", "meningioma", "notumor", "pituitary"]

# ─── SKIN MODEL ────────────────────────────────────────────────────────────────
skin_model = models.resnet18(weights=None)
skin_model.fc = nn.Linear(skin_model.fc.in_features, 2)
skin_model.load_state_dict(torch.load(
    "models/skin_model.pth", map_location="cpu"
))
skin_model = skin_model.to(device)
skin_model.eval()
skin_classes = ["benign", "malignant"]

# ─── GRAD-CAM ──────────────────────────────────────────────────────────────────
from pytorch_grad_cam import GradCAM

brain_cam = GradCAM(model=brain_model, target_layers=[brain_model.layer4[-1]])
skin_cam  = GradCAM(model=skin_model,  target_layers=[skin_model.layer4[-1]])