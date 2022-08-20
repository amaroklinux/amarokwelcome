#!/usr/bin/python3
import apt
import gettext
import gi
import os
import platform
import subprocess
import locale
import cairo
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, Gdk, GdkPixbuf

NORUN_FLAG = os.path.expanduser("~/.amarok/amarokwelcome/norun.flag")

# i18n
gettext.install("amarokwelcome", "/usr/share/amarok/locale")
from locale import gettext as _
locale.bindtextdomain("amarokwelcome", "/usr/share/amarok/locale")
locale.textdomain("amarokwelcome")

LAYOUT_STYLE_LEGACY, LAYOUT_STYLE_NEW = range(2)

class SidebarRow(Gtk.ListBoxRow):

    def __init__(self, page_widget, page_name, icon_name):
        Gtk.ListBoxRow.__init__(self)
        self.page_widget = page_widget
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_border_width(6)
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        box.pack_start(image, False, False, 0)
        label = Gtk.Label()
        label.set_text(page_name)
        box.pack_start(label, False, False, 0)
        self.add(box)

class amarokWelcome:

    def __init__(self):
        builder = Gtk.Builder()
        builder.set_translation_domain("amarokwelcome")
        builder.add_from_file('/usr/share/amarok/amarokwelcome/amarokwelcome.ui')

        window = builder.get_object("main_window")
        window.set_icon_name("amarokwelcome")
        window.set_position(Gtk.WindowPosition.CENTER)
        window.connect("destroy", Gtk.main_quit)

        with open("/etc/amarok/info") as f:
            config = dict([line.strip().split("=") for line in f])
        codename = config['CODENAME'].capitalize()
        edition = config['EDITION'].replace('"', '')
        release = config['RELEASE']
        desktop = config['DESKTOP']
#        release_notes = config['RELEASE_NOTES_URL']
#        new_features = config['NEW_FEATURES_URL']
        architecture = "64-bit"
        if platform.machine() != "x86_64":
            architecture = "32-bit"

        # distro-specific
        dist_name = "Amarok Linux"
        if os.path.exists("/usr/share/doc/debian-system-adjustments/copyright"):
            dist_name = "Amarok"

        # Setup the labels in the Mint badge
        builder.get_object("label_version").set_text("%s %s" % (dist_name, release))
        builder.get_object("label_edition").set_text("%s %s" % (edition, architecture))

        # Setup the main stack
        self.stack = Gtk.Stack()
        builder.get_object("center_box").pack_start(self.stack, True, True, 0)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)

        # Action buttons
        builder.get_object("button_forums").connect("clicked", self.visit, "https://amaroklinux.forumeiros.com")
        builder.get_object("button_contribute").connect("clicked", self.visit, "https://amaroklinux.forumeiros.com")
        builder.get_object("button_update").connect("clicked", self.launch, "gpk-update-viewer")
        builder.get_object("button_amaroksoftware").connect("clicked", self.launch, "amarok-software")
        builder.get_object("button_timeshift").connect("clicked", self.pkexec, "timeshift-gtk")
        builder.get_object("button_gufw").connect("clicked", self.launch, "gufw")
        builder.get_object("button_layout_legacy").connect("clicked", self.on_button_layout_clicked, LAYOUT_STYLE_LEGACY)
        builder.get_object("button_layout_new").connect("clicked", self.on_button_layout_clicked, LAYOUT_STYLE_NEW)

        # Settings button depends on DE
        de_is_cinnamon = False
        self.theme = None
        if os.getenv("XDG_CURRENT_DESKTOP") in ["Cinnamon", "X-Cinnamon"]:
            builder.get_object("button_settings").connect("clicked", self.launch, "cinnamon-settings")
            de_is_cinnamon = True
            self.theme = Gio.Settings(schema="org.cinnamon.desktop.interface").get_string("gtk-theme")
        elif os.getenv("XDG_CURRENT_DESKTOP") == "MATE":
            builder.get_object("button_settings").connect("clicked", self.launch, "mate-control-center")
        elif os.getenv("XDG_CURRENT_DESKTOP") == "XFCE":
            builder.get_object("button_settings").connect("clicked", self.launch, "xfce4-settings-manager")
        elif os.getenv("XDG_CURRENT_DESKTOP") == "BUDGIE":
            builder.get_object("button_settings").connect("clicked", self.launch, "gnome-control-center")
        elif os.getenv("XDG_CURRENT_DESKTOP") == "GNOME":
            builder.get_object("button_settings").connect("clicked", self.launch, "gnome-control-center")
        elif os.getenv("XDG_CURRENT_DESKTOP") == "KDE":
            builder.get_object("button_settings").connect("clicked", self.launch, "systemsettings")
        else:
            # Hide settings
            builder.get_object("box_first_steps").remove(builder.get_object("box_settings"))

        # Hide Cinnamon layout settings in other DEs
        if not de_is_cinnamon:
            builder.get_object("box_first_steps").remove(builder.get_object("box_cinnamon"))

        # Construct the stack switcher
        list_box = builder.get_object("list_navigation")

        page = builder.get_object("page_home")
        self.stack.add_named(page, "page_home")
        list_box.add(SidebarRow(page, _("Welcome"), "go-home-symbolic"))
        self.stack.set_visible_child(page)

        page = builder.get_object("page_first_steps")
        self.stack.add_named(page, "page_first_steps")
        list_box.add(SidebarRow(page, _("First Steps"), "dialog-information-symbolic"))

        page = builder.get_object("page_help")
        self.stack.add_named(page, "page_help")
        list_box.add(SidebarRow(page, _("Help"), "help-browser-symbolic"))

        page = builder.get_object("page_contribute")
        self.stack.add_named(page, "page_contribute")
        list_box.add(SidebarRow(page, _("Contribute"), "starred-symbolic"))

        list_box.connect("row-activated", self.sidebar_row_selected_cb)

        # Construct the bottom toolbar
        box = builder.get_object("toolbar_bottom")
        checkbox = Gtk.CheckButton()
        checkbox.set_label(_("Show this dialog at startup"))
        if not os.path.exists(NORUN_FLAG):
            checkbox.set_active(True)
        checkbox.connect("toggled", self.on_button_toggled)
        box.pack_end(checkbox)

        scale = window.get_scale_factor()

        self.color = "green"
        self.dark_mode = False

        # Use HIDPI pictures if appropriate
        if scale == 1:
            surface = self.surface_for_path("/usr/share/amarok/amarokwelcome/legacy.png", scale)
            builder.get_object("img_legacy").set_from_surface(surface)
            surface = self.surface_for_path("/usr/share/amarok/amarokwelcome/modern.png", scale)
            builder.get_object("img_modern").set_from_surface(surface)
        else:
            surface = self.surface_for_path("/usr/share/amarok/amarokwelcome/legacy-hidpi.png", scale)
            builder.get_object("img_legacy").set_from_surface(surface)
            surface = self.surface_for_path("/usr/share/amarok/amarokwelcome/modern-hidpi.png", scale)
            builder.get_object("img_modern").set_from_surface(surface)

        window.set_default_size(800, 500)
        window.show_all()

    def surface_for_path(self, path, scale):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)

        return Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale)

    def sidebar_row_selected_cb(self, list_box, row):
        self.stack.set_visible_child(row.page_widget)

    def on_button_toggled(self, button):
        if button.get_active():
            if os.path.exists(NORUN_FLAG):
                os.system("rm -rf %s" % NORUN_FLAG)
        else:
            os.system("mkdir -p ~/.amarok/amarokwelcome")
            os.system("touch %s" % NORUN_FLAG)

    def on_button_layout_clicked (self, button, style):

        applets_legacy = ['panel1:left:0:menu@cinnamon.org',
                          'panel1:left:1:show-desktop@cinnamon.org',
                          'panel1:left:2:panel-launchers@cinnamon.org',
                          'panel1:left:3:window-list@cinnamon.org',
                          'panel1:right:0:systray@cinnamon.org',
                          'panel1:right:1:xapp-status@cinnamon.org',
                          'panel1:right:2:keyboard@cinnamon.org',
                          'panel1:right:3:notifications@cinnamon.org',
                          'panel1:right:4:printers@cinnamon.org',
                          'panel1:right:5:removable-drives@cinnamon.org',
                          'panel1:right:6:favorites@cinnamon.org',
                          'panel1:right:7:user@cinnamon.org',
                          'panel1:right:8:network@cinnamon.org',
                          'panel1:right:9:sound@cinnamon.org',
                          'panel1:right:10:power@cinnamon.org',
                          'panel1:right:11:calendar@cinnamon.org']

        applets_new = ['panel1:left:0:menu@cinnamon.org',
                       'panel1:left:1:show-desktop@cinnamon.org',
                       'panel1:left:2:grouped-window-list@cinnamon.org',
                       'panel1:right:0:systray@cinnamon.org',
                       'panel1:right:1:xapp-status@cinnamon.org',
                       'panel1:right:2:notifications@cinnamon.org',
                       'panel1:right:3:printers@cinnamon.org',
                       'panel1:right:4:removable-drives@cinnamon.org',
                       'panel1:right:5:keyboard@cinnamon.org',
                       'panel1:right:6:favorites@cinnamon.org',
                       'panel1:right:7:network@cinnamon.org',
                       'panel1:right:8:sound@cinnamon.org',
                       'panel1:right:9:power@cinnamon.org',
                       'panel1:right:10:calendar@cinnamon.org']

        settings = Gio.Settings("org.cinnamon")
        settings.set_strv("panels-enabled", ['1:0:bottom'])

        applets = applets_new
        left_icon_size = 0
        center_icon_size = 0
        right_icon_size = 0
        if style == LAYOUT_STYLE_LEGACY:
            applets = applets_legacy
            panel_size = 27
            menu_label = "Menu"
        elif style == LAYOUT_STYLE_NEW:
            panel_size = 40
            right_icon_size = 24
            menu_label = ""

        settings.set_strv("panels-height", ['1:%s' % panel_size])
        settings.set_strv("enabled-applets", applets)
        settings.set_string("app-menu-label", menu_label)
        settings.set_string("panel-zone-icon-sizes", "[{\"panelId\": 1, \"left\": %s, \"center\": %s, \"right\": %s}]" % (left_icon_size, center_icon_size, right_icon_size))
        os.system("cinnamon --replace &")

    def on_dark_mode_changed(self, button, state):
        self.dark_mode = state
        self.change_color()

    def on_color_button_clicked(self, button, color):
        self.color = color
        self.change_color()

    def change_color(self):
        theme = "Adapta-Eta"
        wm_theme = "Adapta-Eta"
        cinnamon_theme = "Adapta-Nokto-Eta"
        if self.dark_mode:
            theme = "%s-Eta" % theme
            wm_theme = "Adapta-Nokto-Eta"
        if self.color != "green":
            theme = "%s-%s" % (theme, self.color.title())
            cinnamon_theme = "Adapta-Nokto-Eta-%s" % self.color.title()

        if os.getenv("XDG_CURRENT_DESKTOP") in ["Cinnamon", "X-Cinnamon"]:
            settings = Gio.Settings(schema="org.cinnamon.desktop.interface")
            settings.set_string("gtk-theme", theme)
            settings.set_string("icon-theme", theme)
            Gio.Settings(schema="org.cinnamon.desktop.wm.preferences").set_string("theme", wm_theme)
            Gio.Settings(schema="org.cinnamon.theme").set_string("name", cinnamon_theme)
        elif os.getenv("XDG_CURRENT_DESKTOP") == "MATE":
            settings = Gio.Settings(schema="org.mate.interface")
            settings.set_string("gtk-theme", theme)
            settings.set_string("icon-theme", theme)
            Gio.Settings(schema="org.mate.Marco.general").set_string("theme", wm_theme)
        elif os.getenv("XDG_CURRENT_DESKTOP") == "XFCE":
            subprocess.call(["xfconf-query", "-c", "xsettings", "-p", "/Net/ThemeName", "-s", theme])
            subprocess.call(["xfconf-query", "-c", "xsettings", "-p", "/Net/IconThemeName", "-s", theme])
            subprocess.call(["xfconf-query", "-c", "xfwm4", "-p", "/general/theme", "-s", theme])

    def visit(self, button, url):
        subprocess.Popen(["xdg-open", url])

    def launch(self, button, command):
        subprocess.Popen([command])

    def pkexec(self, button, command):
        subprocess.Popen(["pkexec", command])

if __name__ == "__main__":
    amarokWelcome()
    Gtk.main()