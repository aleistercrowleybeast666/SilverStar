"""Compact offline export entry; expandable details never imply live state."""
from copy import deepcopy
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget
from silverstar_fccg.ui.widgets import CollapsibleSection


class MissionProfilePanel(QWidget):
    exportRequested = Signal()

    def __init__(self, translator):
        super().__init__()
        self._translator = translator
        self._profile = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        self.export_button = QPushButton()
        self.export_button.setObjectName('missionProfileExportButton')
        self.export_button.clicked.connect(lambda _checked=False: self.exportRequested.emit())
        toolbar.addWidget(self.export_button)
        self.availability_label = QLabel()
        self.availability_label.setWordWrap(True)
        toolbar.addWidget(self.availability_label, 1)
        layout.addLayout(toolbar)
        self.lifecycle_label = QLabel()
        self.continuous_label = QLabel()
        self.rules_label = QLabel()
        self.identity_label = QLabel()
        self.scope_label = QLabel()
        for label in (self.lifecycle_label, self.continuous_label, self.rules_label, self.identity_label, self.scope_label):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details = CollapsibleSection(expanded=False)
        details_layout = QVBoxLayout(self.details.body)
        details_layout.setContentsMargins(8, 0, 0, 0)
        for label in (self.scope_label, self.lifecycle_label, self.continuous_label, self.rules_label, self.identity_label):
            details_layout.addWidget(label)
        layout.addWidget(self.details)
        self.Language_Apply(translator)

    def Profile_Set(self, profile):
        self._profile = deepcopy(profile)
        self.Language_Apply(self._translator)

    def Language_Apply(self, translator):
        self._translator = translator
        text = translator.Text_Get
        self.details.Title_Set(text('mission_profile.details'))
        self.export_button.setText(text('mission_profile.export'))
        self.export_button.setEnabled(self._profile is not None)
        self.scope_label.setText(text('mission_profile.scope'))
        self.availability_label.setText(text('mission_profile.available') if self._profile is not None
                                        else text('mission_profile.unavailable'))
        if self._profile is None:
            self.lifecycle_label.setText(text('mission_profile.unavailable'))
            self.continuous_label.clear(); self.rules_label.clear(); self.identity_label.clear()
            return
        profile = self._profile
        names = [text('mission_profile.state.' + row['type_id']) for row in profile['lifecycle']['states']]
        self.lifecycle_label.setText(text('mission_profile.lifecycle', states=' / '.join(names)))
        owners = profile['continuous']
        self.continuous_label.setText(text('mission_profile.continuous',
            ins=owners['ins']['plugin_id'] if owners['ins'] else '—',
            estimator=owners['estimator']['plugin_id'] if owners['estimator'] else '—'))
        rules = ', '.join(row['slot'] + ':' + row['option'] for row in profile['rules'] if row['enabled']) or '—'
        self.rules_label.setText(text('mission_profile.rules', rules=rules))
        self.identity_label.setText(text('mission_profile.identity', digest=profile['sha256']))
