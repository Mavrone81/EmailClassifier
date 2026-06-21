"""EmailClassifier — categorise and clean a Gmail mailbox.

Public API:
    from email_classifier import Classifier, load_categories, Cleaner
"""
from .categories import Category, Rule, load_categories, DEFAULT_CONFIG_PATH
from .classifier import Classifier, Classification
from .cleaner import Cleaner, CleanAction, CleanPlan

__version__ = "1.0.0"

__all__ = [
    "Category",
    "Rule",
    "load_categories",
    "DEFAULT_CONFIG_PATH",
    "Classifier",
    "Classification",
    "Cleaner",
    "CleanAction",
    "CleanPlan",
]
