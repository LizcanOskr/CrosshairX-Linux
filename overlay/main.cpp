#include <LayerShellQt/window.h>
#include <KGlobalAccel>
#include <KWindowEffects>

#include <QApplication>
#include <QAction>
#include <QFile>
#include <QHash>
#include <QJsonDocument>
#include <QJsonObject>
#include <QKeySequence>
#include <QPainter>
#include <QSaveFile>
#include <QScreen>
#include <QTimer>
#include <QWidget>

class Overlay final : public QWidget
{
public:
    explicit Overlay(QString settingsPath)
        : settingsPath_(std::move(settingsPath))
    {
        setWindowFlags(Qt::Window | Qt::FramelessWindowHint |
                       Qt::WindowDoesNotAcceptFocus | Qt::WindowTransparentForInput);
        setAttribute(Qt::WA_TranslucentBackground);
        setAttribute(Qt::WA_TransparentForMouseEvents);
        setAttribute(Qt::WA_ShowWithoutActivating);
        setAutoFillBackground(false);

        // Crea primero el QWindow para que LayerShellQt pueda asociarle el rol.
        winId();
        layer_ = LayerShellQt::Window::get(windowHandle());
        if (layer_) {
            layer_->setLayer(LayerShellQt::Window::LayerOverlay);
            LayerShellQt::Window::Anchors anchors;
            anchors |= LayerShellQt::Window::AnchorTop;
            anchors |= LayerShellQt::Window::AnchorBottom;
            anchors |= LayerShellQt::Window::AnchorLeft;
            anchors |= LayerShellQt::Window::AnchorRight;
            layer_->setAnchors(anchors);
            layer_->setMargins(QMargins(0, 0, 0, 0));
            layer_->setExclusiveZone(0);
            layer_->setKeyboardInteractivity(
                LayerShellQt::Window::KeyboardInteractivityNone);
            layer_->setActivateOnShow(false);
            layer_->setScope(QStringLiteral("crosshairx-linux"));
        } else {
            qFatal("No se pudo asociar el rol de LayerShellQt a la superficie Wayland");
        }
        disableBlurBehind();

        connect(&timer_, &QTimer::timeout, this, [this] { readSettings(); });
        timer_.start(150);
        registerVisibilityShortcut();
        readSettings();
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        if (!visible_)
            return;

        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing, true);
        const QPointF center(width() / 2.0 + xOffset_, height() / 2.0 + yOffset_);
        const qreal half = size_ / 2.0;
        const qreal gap = gap_;

        auto stroke = [&](qreal extra, const QColor &color) {
            QPen pen(color);
            pen.setWidthF(qMax<qreal>(0.1, thickness_ + extra));
            pen.setCapStyle(Qt::RoundCap);
            pen.setJoinStyle(Qt::RoundJoin);
            painter.setPen(pen);
            painter.setBrush(Qt::NoBrush);
            drawShape(painter, center, half, gap);
        };
        if (outline_) stroke(qMax<qreal>(1.0, thickness_), QColor(0, 0, 0, 230));
        stroke(0, color_);
    }

private:
    void registerMovementShortcuts(const QJsonObject &settings)
    {
        struct MovementShortcut {
            const char *setting;
            const char *name;
            const char *label;
            const char *defaultSequence;
            int dx;
            int dy;
        };
        static constexpr MovementShortcut shortcuts[] = {
            {"move_left_shortcut", "moveLeft", "Mover mira a la izquierda", "Home", -1, 0},
            {"move_right_shortcut", "moveRight", "Mover mira a la derecha", "End", 1, 0},
            {"move_up_shortcut", "moveUp", "Mover mira arriba", "PgUp", 0, -1},
            {"move_down_shortcut", "moveDown", "Mover mira abajo", "PgDown", 0, 1},
        };
        auto *accel = KGlobalAccel::self();
        for (const auto &entry : shortcuts) {
            const QString setting = QString::fromLatin1(entry.setting);
            const QString sequenceText = settings.value(setting)
                .toString(QString::fromLatin1(entry.defaultSequence));
            if (registeredMovementShortcuts_.value(setting) == sequenceText
                && registeredMovementShortcuts_.contains(setting))
                continue;

            QAction *action = movementActions_.value(setting, nullptr);
            if (!action) {
                action = new QAction(this);
                action->setObjectName(QString::fromLatin1(entry.name));
                action->setText(QString::fromLatin1(entry.label));
                connect(action, &QAction::triggered, this,
                        [this, dx = entry.dx, dy = entry.dy] {
                            moveCrosshair(dx, dy);
                        });
                movementActions_.insert(setting, action);
            }

            const QKeySequence sequence = QKeySequence::fromString(
                sequenceText, QKeySequence::PortableText);
            const QList<QKeySequence> assigned = sequence.isEmpty()
                ? QList<QKeySequence>{} : QList<QKeySequence>{sequence};
            accel->setDefaultShortcut(action, assigned, KGlobalAccel::NoAutoloading);
            if (sequence.isEmpty()) {
                accel->removeAllShortcuts(action);
            } else if (!accel->setShortcut(
                           action, assigned, KGlobalAccel::NoAutoloading)) {
                qWarning("No se pudo registrar el atajo global %s",
                         entry.label);
            }
            registeredMovementShortcuts_.insert(setting, sequenceText);
        }
    }

    void registerVisibilityShortcut()
    {
        auto *action = new QAction(this);
        action->setObjectName(QStringLiteral("toggleCrosshairVisibility"));
        action->setText(QStringLiteral("Activar o desactivar la mira"));
        const QList<QKeySequence> shortcut{
            QKeySequence(Qt::CTRL | Qt::ALT | Qt::Key_masculine)};
        auto *accel = KGlobalAccel::self();
        accel->setDefaultShortcut(action, shortcut);
        if (!accel->setShortcut(action, shortcut))
            qWarning("No se pudo registrar el atajo global para alternar la mira");
        connect(action, &QAction::triggered, this, [this] { toggleVisibility(); });
    }

    void toggleVisibility()
    {
        QFile file(settingsPath_);
        if (!file.open(QIODevice::ReadOnly))
            return;
        QJsonObject settings = QJsonDocument::fromJson(file.readAll()).object();
        file.close();
        settings.insert(QStringLiteral("visible"), !settings.value("visible").toBool(true));

        QSaveFile output(settingsPath_);
        if (!output.open(QIODevice::WriteOnly))
            return;
        output.write(QJsonDocument(settings).toJson(QJsonDocument::Indented));
        if (output.commit())
            readSettings();
    }

    void moveCrosshair(int dx, int dy)
    {
        if (!visible_)
            return;

        QFile file(settingsPath_);
        if (!file.open(QIODevice::ReadOnly))
            return;
        QJsonObject settings = QJsonDocument::fromJson(file.readAll()).object();
        file.close();
        const int x = settings.value("x_offset").toInt(xOffset_);
        const int y = settings.value("y_offset").toInt(yOffset_);
        xOffset_ = qBound(-8192, x + dx, 8192);
        yOffset_ = qBound(-8192, y + dy, 8192);
        settings.insert(QStringLiteral("x_offset"), xOffset_);
        settings.insert(QStringLiteral("y_offset"), yOffset_);

        QSaveFile output(settingsPath_);
        if (output.open(QIODevice::WriteOnly)) {
            output.write(QJsonDocument(settings).toJson(QJsonDocument::Indented));
            output.commit();
        }
        update();
    }

    void drawShape(QPainter &p, const QPointF &c, qreal half, qreal gap)
    {
        if (shape_ == QStringLiteral("Punto")) {
            p.setBrush(p.pen().color());
            p.drawEllipse(c, qMax<qreal>(0.5, half), qMax<qreal>(0.5, half));
        } else if (shape_ == QStringLiteral("Círculo")) {
            p.drawEllipse(c, half, half);
        } else if (shape_ == QStringLiteral("T")) {
            p.drawLine(QPointF(c.x() - half, c.y() - half),
                       QPointF(c.x() + half, c.y() - half));
            p.drawLine(QPointF(c.x(), c.y() - half), QPointF(c.x(), c.y() + half));
        } else {
            p.drawLine(QPointF(c.x() - half, c.y()), QPointF(c.x() - gap, c.y()));
            p.drawLine(QPointF(c.x() + gap, c.y()), QPointF(c.x() + half, c.y()));
            p.drawLine(QPointF(c.x(), c.y() - half), QPointF(c.x(), c.y() - gap));
            p.drawLine(QPointF(c.x(), c.y() + gap), QPointF(c.x(), c.y() + half));
        }
    }

    void readSettings()
    {
        QFile file(settingsPath_);
        if (!file.open(QIODevice::ReadOnly))
            return;
        const QJsonObject s = QJsonDocument::fromJson(file.readAll()).object();
        registerMovementShortcuts(s);
        const int screenIndex = s.value("screen").toInt(0);
        const auto screens = QGuiApplication::screens();
        if (!screens.isEmpty()) {
            const int bounded = qBound(0, screenIndex, screens.size() - 1);
            QScreen *screen = screens.at(bounded);
            if (layer_ && layer_->screen() != screen)
                layer_->setScreen(screen);
            if (windowHandle() && windowHandle()->screen() != screen)
                windowHandle()->setScreen(screen);
            if (size() != screen->geometry().size())
                resize(screen->geometry().size());
        }

        const bool wasVisible = visible_;
        visible_ = s.value("visible").toBool(true);
        shape_ = s.value("shape").toString(QStringLiteral("Cruz"));
        const QColor newColor(s.value("color").toString(QStringLiteral("#00ff66")));
        if (newColor.isValid()) color_ = newColor;
        size_ = qBound(1, s.value("size").toInt(48), 256);
        gap_ = qBound(0, s.value("gap").toInt(5), 128);
        thickness_ = qBound<qreal>(0.25, s.value("thickness").toDouble(1.5), 8.0);
        outline_ = s.value("outline").toBool(true);
        xOffset_ = s.value("x_offset").toInt(0);
        yOffset_ = s.value("y_offset").toInt(0);

        if (visible_ && !isVisible()) {
            show();
            // Qt/Wayland termina de mapear la superficie después de show().
            // Reafirmamos que no tenga región de blur una vez creada.
            QTimer::singleShot(0, this, [this] { disableBlurBehind(); });
            QTimer::singleShot(100, this, [this] { disableBlurBehind(); });
            QTimer::singleShot(500, this, [this] { disableBlurBehind(); });
        }
        else if (!visible_ && isVisible()) hide();
        if (wasVisible != visible_ || visible_) update();
    }

    void disableBlurBehind()
    {
        if (windowHandle())
            KWindowEffects::enableBlurBehind(windowHandle(), false);
    }

    QString settingsPath_;
    QHash<QString, QAction *> movementActions_;
    QHash<QString, QString> registeredMovementShortcuts_;
    LayerShellQt::Window *layer_ = nullptr;
    QTimer timer_;
    QString shape_ = QStringLiteral("Cruz");
    QColor color_ = QColor(QStringLiteral("#00ff66"));
    int size_ = 48;
    int gap_ = 5;
    qreal thickness_ = 1.5;
    int xOffset_ = 0;
    int yOffset_ = 0;
    bool outline_ = true;
    bool visible_ = true;
};

int main(int argc, char **argv)
{
    qputenv("QT_QPA_PLATFORM", "wayland");
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");
    QApplication app(argc, argv);
    // Kvantum solicita blur para superficies translúcidas. El renderizador
    // solo dibuja la mira, así que usa Fusion para conservar el alfa sin blur.
    app.setStyle(QStringLiteral("Fusion"));
    // Fija un app_id estable para la superficie en el compositor.
    app.setApplicationName(QStringLiteral("crosshairx-linux"));
    app.setDesktopFileName(QStringLiteral("crosshairx-linux"));
    if (app.platformName() != QStringLiteral("wayland"))
        return 2;
    const QString path = argc > 1 ? QString::fromLocal8Bit(argv[1]) : QString();
    if (path.isEmpty())
        return 2;
    Overlay overlay(path);
    return app.exec();
}
