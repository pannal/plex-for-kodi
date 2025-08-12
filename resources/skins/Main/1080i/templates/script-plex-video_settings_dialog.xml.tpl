{% extends "base.xml.tpl" %}
{% block backgroundcolor %}{% endblock %}
{% block controls %}
<control type="group">
    <visible>String.IsEmpty(Window.Property(is_plextuary)) + !String.IsEmpty(Window.Property(via.OSD)) + !Window.IsVisible(sliderdialog)</visible>
    <animation effect="fade" start="100" end="0">Hidden</animation>
    <posx>0</posx>
    <posy>0</posy>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>1920</width>
        <height>1080</height>
        <texture>script.plex/player-fade.png</texture>
        <colordiffuse>FF080808</colordiffuse>
    </control>
</control>
<control type="group">
    <visible>!Window.IsVisible(sliderdialog) + !Window.IsVisible(osdvideosettings) + !Window.IsVisible(osdaudiosettings) + !Window.IsVisible(osdsubtitlesettings) + !Window.IsVisible(subtitlesearch) + !Window.IsActive(selectdialog) + !Window.IsVisible(osdcmssettings)</visible>
    <posx>460</posx>
    <posy>{{ vperc(vscale(600)) }}</posy>
    <control type="image">
        <posx>-40</posx>
        <posy>{{ vscale(-40) }}</posy>
        <width>1080</width>
        <height>{{ vscale(770) }}</height>
        <texture border="42">script.plex/drop-shadow.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>1000</width>
        <height>{{ vscale(80) }}</height>
        <texture border="10">script.plex/white-square-top-rounded.png</texture>
        <colordiffuse>F21F1F1F</colordiffuse>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>{{ vscale(80) }}</posy>
        <width>1000</width>
        <height>{{ vscale(610) }}</height>
        <texture flipy="true" border="10">script.plex/white-square-top-rounded.png</texture>
        <colordiffuse>D3111111</colordiffuse>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>{{ vscale(80) }}</posy>
        <width>400</width>
        <height>{{ vscale(610) }}</height>
        <texture flipy="true" border="10">script.plex/white-square-tl-rounded.png</texture>
        <colordiffuse>30000000</colordiffuse>
    </control>
    <control type="label">
        <posx>0</posx>
        <posy>0</posy>
        <width>1000</width>
        <height>{{ vscale(80) }}</height>
        <font>font12</font>
        <align>center</align>
        <aligny>center</aligny>
        <textcolor>FFFFFFFF</textcolor>
        <label>[B][UPPERCASE]$INFO[Window.Property(heading)][/UPPERCASE][/B]</label>
    </control>
    <control type="list" id="100">
        <posx>0</posx>
        <posy>{{ vscale(80) }}</posy>
        <width>990</width>
        <height>{{ vscale(600) }}</height>
        <onup>noop</onup>
        <ondown>noop</ondown>
        <scrolltime>200</scrolltime>
        <orientation>vertical</orientation>
        <pagecontrol>101</pagecontrol>
        <onright>101</onright>
        <!-- ITEM LAYOUT ########################################## -->
        <itemlayout height="{{ vscale(100) }}">
            <control type="label">
                <posx>20</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(100) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <scroll>true</scroll>
                <scrollspeed>15</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="label">
                <posx>320</posx>
                <posy>0</posy>
                <width>650</width>
                <height>{{ vscale(100) }}</height>
                <font>font12</font>
                <align>right</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <scroll>true</scroll>
                <scrollspeed>15</scrollspeed>
                <label>$INFO[ListItem.Label2]</label>
            </control>
        </itemlayout>
        <focusedlayout height="{{ vscale(100) }}">
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>1000</width>
                <height>{{ vscale(100) }}</height>
                <texture colordiffuse="FFE5A00D">script.plex/white-square.png</texture>
            </control>
            <control type="label">
                <posx>20</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(100) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FF000000</textcolor>
                <scroll>true</scroll>
                <scrollspeed>15</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="label">
                <posx>320</posx>
                <posy>0</posy>
                <width>650</width>
                <height>{{ vscale(100) }}</height>
                <font>font12</font>
                <align>right</align>
                <aligny>center</aligny>
                <textcolor>FF000000</textcolor>
                <scroll>true</scroll>
                <scrollspeed>15</scrollspeed>
                <label>$INFO[ListItem.Label2]</label>
            </control>
        </focusedlayout>
    </control>
</control>
<control type="scrollbar" id="101">
    <hitrect x="1108" y="33" w="90" h="734" />
    <left>1450</left>
    <top>{{ vperc(vscale(600)) + vscale(80) }}</top>
    <width>10</width>
    <height>{{ vscale(600) }}</height>
    <onleft>100</onleft>
    <visible>!Window.IsVisible(sliderdialog) + Control.IsVisible(100) + !Window.IsVisible(osdvideosettings) + !Window.IsVisible(osdaudiosettings) + !Window.IsVisible(osdsubtitlesettings) + !Window.IsVisible(subtitlesearch) + !Window.IsVisible(osdcmssettings)</visible>
    <texturesliderbackground colordiffuse="30000000" border="5">script.plex/white-square.png</texturesliderbackground>
    <texturesliderbar colordiffuse="33FFFFFF" border="5">script.plex/white-square.png</texturesliderbar>
    <texturesliderbarfocus colordiffuse="FFE5A00D" border="5">script.plex/white-square.png</texturesliderbarfocus>
    <textureslidernib>-</textureslidernib>
    <textureslidernibfocus>-</textureslidernibfocus>
    <pulseonselect>false</pulseonselect>
    <orientation>vertical</orientation>
    <showonepage>false</showonepage>
    <onleft>100</onleft>
</control>
{% endblock controls %}