// SPDX-FileCopyrightText: 2019-2025 Connor McLaughlin <stenzek@gmail.com>
// SPDX-License-Identifier: CC-BY-NC-ND-4.0

#pragma once

#include <QtWidgets/QWidget>

class SettingsWindow;
class QCheckBox;
class QLabel;
class QSlider;

class SISESettingsWidget : public QWidget
{
  Q_OBJECT

public:
  SISESettingsWidget(SettingsWindow* dialog, QWidget* parent);

private:
  QCheckBox* m_enabled;
  QCheckBox* m_showOverlay;
  QCheckBox* m_zScaleEnabled;
  QSlider* m_scaleSlider;
  QLabel* m_scaleLabel;
  QLabel* m_statusLabel;

  void onEnabledChanged(Qt::CheckState state);
  void updateStatus();
};
