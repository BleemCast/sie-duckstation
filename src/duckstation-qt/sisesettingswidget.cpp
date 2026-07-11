// SPDX-FileCopyrightText: 2019-2025 Connor McLaughlin <stenzek@gmail.com>
// SPDX-License-Identifier: CC-BY-NC-ND-4.0

#include "sisesettingswidget.h"
#include "qthost.h"
#include "qtutils.h"
#include "settingswindow.h"
#include "settingwidgetbinder.h"

#include "core/core.h"

#include <QtWidgets/QCheckBox>
#include <QtWidgets/QFormLayout>
#include <QtWidgets/QGroupBox>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QSlider>
#include <QtWidgets/QVBoxLayout>

SISESettingsWidget::SISESettingsWidget(SettingsWindow* dialog, QWidget* parent)
  : QWidget(parent)
{
  auto* mainLayout = new QVBoxLayout(this);

  auto* group = new QGroupBox(tr("SIE — Enhanced Draw Distance"), this);
  auto* layout = new QFormLayout(group);

  m_enabled = new QCheckBox(tr("Enable SIE (MIPS Culling Patcher)"), group);
  SettingWidgetBinder::BindWidgetToBoolSetting(nullptr, m_enabled, "sise", "enabled", false);
  layout->addRow(m_enabled);

  m_showOverlay = new QCheckBox(tr("Show status overlay"), group);
  SettingWidgetBinder::BindWidgetToBoolSetting(nullptr, m_showOverlay, "sise", "show_overlay", true);
  layout->addRow(m_showOverlay);

  // Z-scaling section
  auto* zGroup = new QGroupBox(tr("Z-Scaling (Experimental — may garble some games)"), group);
  auto* zLayout = new QFormLayout(zGroup);

  m_zScaleEnabled = new QCheckBox(tr("Enable Z-Scaling"), zGroup);
  SettingWidgetBinder::BindWidgetToBoolSetting(nullptr, m_zScaleEnabled, "sise", "z_scale_enabled", false);
  zLayout->addRow(m_zScaleEnabled);

  auto* scaleLayout = new QHBoxLayout();
  m_scaleSlider = new QSlider(Qt::Horizontal, zGroup);
  m_scaleSlider->setRange(1, 16);
  m_scaleSlider->setValue(4);
  m_scaleSlider->setTickInterval(1);
  m_scaleSlider->setTickPosition(QSlider::TicksBelow);
  m_scaleLabel = new QLabel("4x", zGroup);
  m_scaleLabel->setMinimumWidth(40);
  scaleLayout->addWidget(m_scaleSlider);
  scaleLayout->addWidget(m_scaleLabel);
  auto* scaleRow = new QWidget(zGroup);
  scaleRow->setLayout(scaleLayout);
  zLayout->addRow(tr("Z-Scale multiplier:"), scaleRow);

  m_scaleSlider->setToolTip(tr("Scales the Z-depth value the game reads for culling.\n"
                                "Only affects distant geometry (Z > 200).\n"
                                "4x = 4x draw distance. May garble some games."));

  layout->addRow(zGroup);

  // Status
  m_statusLabel = new QLabel(group);
  m_statusLabel->setWordWrap(true);
  m_statusLabel->setStyleSheet("padding: 8px; background: rgba(0,0,0,0.1); border-radius: 4px;");
  layout->addRow(tr("Status:"), m_statusLabel);

  mainLayout->addWidget(group);
  mainLayout->addStretch(1);

  connect(m_enabled, &QCheckBox::checkStateChanged, this, &SISESettingsWidget::onEnabledChanged);
  connect(m_zScaleEnabled, &QCheckBox::checkStateChanged, this, &SISESettingsWidget::onEnabledChanged);
  connect(m_scaleSlider, &QSlider::valueChanged, this, [this](int val) {
    m_scaleLabel->setText(QString("%1x").arg(val));
    Core::SetBaseFloatSettingValue("sise", "z_scale_factor", static_cast<float>(val));
    updateStatus();
  });
  updateStatus();
}

void SISESettingsWidget::onEnabledChanged(Qt::CheckState state)
{
  updateStatus();
}

void SISESettingsWidget::updateStatus()
{
  QString status;
  if (!m_enabled->isChecked()) {
    status = tr("<b style='color:gray'>DISABLED</b> — Original draw distance.");
  } else {
    QStringList parts;
    parts << tr("<b style='color:green'>ACTIVE</b>");
    parts << tr("MIPS scanner: scanning code for culling instructions");
    if (m_zScaleEnabled->isChecked()) {
      int scale = m_scaleSlider->value();
      parts << tr("Z-Scaling: %1x (experimental)").arg(scale);
    }
    status = parts.join(" | ");
  }
  m_statusLabel->setText(status);
}
#include "moc_sisesettingswidget.cpp"
