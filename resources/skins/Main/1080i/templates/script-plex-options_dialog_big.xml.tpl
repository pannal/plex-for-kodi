{% extends "base.xml.tpl" %}
{% block headers %}<defaultcontrol>1001</defaultcontrol>{% endblock %}
{% block backgroundcolor %}{% endblock %}
{% block controls %}
<control type="image">
    <posx>0</posx>
    <posy>0</posy>
    <width>1920</width>
    <height>1080</height>
    <texture colordiffuse="99606060" border="10">script.plex/white-square.png</texture>
</control>
<control type="group">
    <visible>!String.IsEmpty(Window.Property(initialized))</visible>
    <posx>585</posx>
    <posy>{{ vperc(vscale(640)) }}</posy>
    <control type="image">
        <posx>-40</posx>
        <posy>{{ vscale(-40) }}</posy>
        <width>830</width>
        <height>{{ vscale(640) }}</height>
        <texture border="42">script.plex/drop-shadow.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>750</width>
        <height>{{ vscale(560) }}</height>
        <texture colordiffuse="EE323232" border="10">script.plex/white-square-rounded.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>750</width>
        <height>{{ vscale(80) }}</height>
        <texture colordiffuse="99000000" border="10">script.plex/white-square-top-rounded.png</texture>
    </control>

    <control type="image">
        <posx>48</posx>
        <posy>{{ vscale(31) }}</posy>
        <width>19</width>
        <height>{{ vscale(19) }}</height>
        <texture colordiffuse="FFE5A00D">script.plex/indicators/circle-19.png</texture>
    </control>

    <control type="label">
        <posx>115</posx>
        <posy>0</posy>
        <width>575</width>
        <height>{{ vscale(80) }}</height>
        <font>font12</font>
        <align>left</align>
        <aligny>center</aligny>
        <textcolor>FFE5A00D</textcolor>
        <label>$INFO[Window.Property(header)]</label>
    </control>

    <control type="textbox">
        <posx>115</posx>
        <posy>{{ vscale(105) }}</posy>
        <width>575</width>
        <height>{{ vscale(325) }}</height>
        <font>font10</font>
        <align>left</align>
        <textcolor>FFFFFFFF</textcolor>
        <scrolltime>200</scrolltime>
        <autoscroll delay="3000" time="3000" repeat="3000"></autoscroll>
        <label>$INFO[Window.Property(info)]</label>
    </control>

    <control type="grouplist" id="100">
        <defaultcontrol always="true">1001</defaultcontrol>
        <posx>-10</posx>
        <posy>{{ vscale(420) }}</posy>
        <width>770</width>
        <height>{{ vscale(155) }}</height>
        <align>center</align>
        <itemgap>-50</itemgap>
        <orientation>horizontal</orientation>
        <scrolltime>0</scrolltime>
        <usecontrolcoords>true</usecontrolcoords>
        <control type="button" id="1001">
            <visible allowhiddenfocus="true">!String.IsEmpty(Window.Property(button.0))</visible>
            <enable>String.IsEmpty(Window.Property(delay_buttons)) | !String.IsEmpty(Window.Property(enable_buttons))</enable>
            <animation effect="zoom" start="100" end="110,120" time="100" center="auto" reversible="false">Focus</animation>
            <animation effect="zoom" start="110,120" end="100" time="100" center="auto" reversible="false">UnFocus</animation>
            <posx>0</posx>
            <posy>0</posy>
            <width min="120">auto</width>
            <height>{{ vscale(143, 1.1) }}</height>
            <font>font10</font>
            <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/buttons/blank-focus.png</texturefocus>
            <texturenofocus colordiffuse="99FFFFFF" border="50">script.plex/buttons/blank.png</texturenofocus>
            <textoffsetx>70</textoffsetx>
            <textcolor>FF000000</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <label>$INFO[Window.Property(button.0)]</label>
        </control>
        <control type="button" id="1002">
            <visible>!String.IsEmpty(Window.Property(button.1))</visible>
            <enable>String.IsEmpty(Window.Property(delay_buttons)) | !String.IsEmpty(Window.Property(enable_buttons))</enable>
            <animation effect="zoom" start="100" end="110,120" time="100" center="auto" reversible="false">Focus</animation>
            <animation effect="zoom" start="110,120" end="100" time="100" center="auto" reversible="false">UnFocus</animation>
            <posx>0</posx>
            <posy>0</posy>
            <width min="120">auto</width>
            <height>{{ vscale(143, 1.1) }}</height>
            <font>font10</font>
            <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/buttons/blank-focus.png</texturefocus>
            <texturenofocus colordiffuse="99FFFFFF" border="50">script.plex/buttons/blank.png</texturenofocus>
            <textoffsetx>70</textoffsetx>
            <textcolor>FF000000</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <label>$INFO[Window.Property(button.1)]</label>
        </control>
        <control type="button" id="1003">
            <visible>!String.IsEmpty(Window.Property(button.2))</visible>
            <enable>String.IsEmpty(Window.Property(delay_buttons)) | !String.IsEmpty(Window.Property(enable_buttons))</enable>
            <animation effect="zoom" start="100" end="110,120" time="100" center="auto" reversible="false">Focus</animation>
            <animation effect="zoom" start="110,120" end="100" time="100" center="auto" reversible="false">UnFocus</animation>
            <posx>0</posx>
            <posy>0</posy>
            <width min="120">auto</width>
            <height>{{ vscale(143, 1.1) }}</height>
            <font>font10</font>
            <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/buttons/blank-focus.png</texturefocus>
            <texturenofocus colordiffuse="99FFFFFF" border="50">script.plex/buttons/blank.png</texturenofocus>
            <textoffsetx>70</textoffsetx>
            <textcolor>FF000000</textcolor>
            <focusedcolor>FF000000</focusedcolor>
            <label>$INFO[Window.Property(button.2)]</label>
        </control>
    </control>

</control>
{% endblock controls %}