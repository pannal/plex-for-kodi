{% extends "base.xml.tpl" %}
{% block backgroundcolor %}{% endblock %}
{% block headers %}
<onload>SetProperty(dropdown,1)</onload>
<defaultcontrol>100</defaultcontrol>
<zorder>100</zorder>
{% endblock %}
{% block controls %}
<control type="button" id="700">
    <!-- dummy for clicks off list -->
    <posx>0</posx>
    <posy>0</posy>
    <width>1920</width>
    <height>1080</height>
    <texturefocus>-</texturefocus>
    <texturenofocus>-</texturenofocus>
</control>
<control type="group" id="100">
    <defaultcontrol>250</defaultcontrol>
    <visible>!String.IsEmpty(Window.Property(show))</visible>
    <posx>0</posx>
    <posy>0</posy>
    <control type="image" id="110">
        <posx>-40</posx>
        <posy>{{ vscale(-40) }}</posy>
        <width>380</width>
        <height>{{ vscale(146) }}</height>
        <texture border="42">script.plex/drop-shadow.png</texture>
    </control>
    <control type="list" id="250">
        <posx>0</posx>
        <posy>0</posy>
        <width>300</width>
        <height>{{ vscale(924) }}</height>
        <onup condition="String.IsEqual(Window.Property(close.direction),top)">Close</onup>
        <onup condition="!String.IsEqual(Window.Property(close.direction),top)">noop</onup>
        <onleft condition="String.IsEqual(Window.Property(close.direction),left)">Close</onleft>
        <onright condition="!String.IsEmpty(Window.Property(scroll))">1152</onright>
        <onright condition="String.IsEqual(Window.Property(close.direction),right)">Close</onright>
        <ondown condition="String.IsEqual(Window.Property(close.direction),down)">Close</ondown>
        <ondown condition="!String.IsEqual(Window.Property(close.direction),down)">noop</ondown>
        <scrolltime>200</scrolltime>
        <orientation>vertical</orientation>
        <pagecontrol>1152</pagecontrol>
        <!-- ITEM LAYOUT ########################################## -->
        <itemlayout height="{{ vscale(66) }}">
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(first))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="D3111111" border="10">script.plex/white-square-top-rounded.png</texture>
            </control>
            <control type="image">
                <visible>String.IsEmpty(ListItem.Property(first)) + String.IsEmpty(ListItem.Property(last)) + String.IsEmpty(ListItem.Property(only))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="D3111111">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(last))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <texture flipy="true" colordiffuse="D3111111" border="10">script.plex/white-square-top-rounded.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(only))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="D3111111" border="10">script.plex/white-square-rounded.png</texture>
            </control>
            <control type="label">
                <visible>String.IsEmpty(ListItem.Property(with.indicator))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <font>font12</font>
                <align>center</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <scroll>true</scroll>
                <scrollspeed>60</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="group">
                <visible>!String.IsEmpty(ListItem.Property(with.indicator))</visible>
                <control type="label">
                    <posx>20</posx>
                    <posy>0</posy>
                    <width>280</width>
                    <height>{{ vscale(66) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FFFFFFFF</textcolor>
                    <scroll>true</scroll>
                    <scrollspeed>60</scrollspeed>
                    <label>$INFO[ListItem.Label]</label>
                </control>
                <control type="image">
                    <posx>254</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>26</width>
                    <height>{{ vscale(26) }}</height>
                    <texture colordiffuse="FFFFFFFF">$INFO[ListItem.Thumb]</texture>
                    <aspectratio>keep</aspectratio>
                </control>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(separator))</visible>
                <posx>0</posx>
                <posy>{{ vscale(64) }}</posy>
                <width>300</width>
                <height>{{ vscale(2) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
        </itemlayout>
        <focusedlayout height="{{ vscale(66) }}">
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(first))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="FFE5A00D" border="10">script.plex/white-square-top-rounded.png</texture>
            </control>
            <control type="image">
                <visible>String.IsEmpty(ListItem.Property(first)) + String.IsEmpty(ListItem.Property(last)) + String.IsEmpty(ListItem.Property(only))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="FFE5A00D">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(last))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <texture flipy="true" colordiffuse="FFE5A00D" border="10">script.plex/white-square-top-rounded.png</texture>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(only))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <texture colordiffuse="FFE5A00D" border="10">script.plex/white-square-rounded.png</texture>
            </control>
            <control type="label">
                <visible>String.IsEmpty(ListItem.Property(with.indicator))</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>300</width>
                <height>{{ vscale(66) }}</height>
                <font>font12</font>
                <align>center</align>
                <aligny>center</aligny>
                <textcolor>FF000000</textcolor>
                <scroll>true</scroll>
                <scrollspeed>60</scrollspeed>
                <label>$INFO[ListItem.Label]</label>
            </control>
            <control type="group">
                <visible>!String.IsEmpty(ListItem.Property(with.indicator))</visible>
                <control type="label">
                    <posx>20</posx>
                    <posy>0</posy>
                    <width>280</width>
                    <height>{{ vscale(66) }}</height>
                    <font>font12</font>
                    <align>left</align>
                    <aligny>center</aligny>
                    <textcolor>FF000000</textcolor>
                    <scroll>true</scroll>
                    <scrollspeed>60</scrollspeed>
                    <label>$INFO[ListItem.Label]</label>
                </control>
                <control type="image">
                    <posx>254</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>26</width>
                    <height>{{ vscale(26) }}</height>
                    <texture colordiffuse="FF000000">$INFO[ListItem.Thumb]</texture>
                    <aspectratio>keep</aspectratio>
                </control>
            </control>
            <control type="image">
                <visible>!String.IsEmpty(ListItem.Property(separator))</visible>
                <posx>0</posx>
                <posy>{{ vscale(64) }}</posy>
                <width>300</width>
                <height>{{ vscale(2) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
        </focusedlayout>
    </control>
    <control type="scrollbar" id="1152">
        <visible>!String.IsEmpty(Window.Property(scroll))</visible>
        <left>300</left>
        <top>0</top>
        <width>6</width>
        <height>{{ vscale(924) }}</height>
        <visible>true</visible>
        <texturesliderbackground colordiffuse="40000000">script.plex/white-square.png</texturesliderbackground>
        <texturesliderbar colordiffuse="FFAAAAAA">script.plex/white-square.png</texturesliderbar>
        <texturesliderbarfocus colordiffuse="FFE5A00D">script.plex/white-square.png</texturesliderbarfocus>
        <textureslidernib colordiffuse="FFAAAAAA">script.plex/white-square.png</textureslidernib>
        <textureslidernibfocus colordiffuse="FFE5A00D">script.plex/white-square.png</textureslidernibfocus>
        <pulseonselect>true</pulseonselect>
        <orientation>vertical</orientation>
        <showonepage>false</showonepage>
        <onleft>250</onleft>
    </control>
</control>
{% endblock controls %}