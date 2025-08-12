{% extends "base.xml.tpl" %}
{% block controls %}
{% include "includes/default_background.xml.tpl" with background_source="$INFO[Player.Art(landscape)]" %}

<control type="group" id="50">
    <posx>0</posx>
    <posy>0</posy>
    <defaultcontrol>101</defaultcontrol>

    <control type="group">
        <posx>90</posx>
        <posy>0</posy>
        <control type="image">
            <posx>-15</posx>
            <posy>{{ vscale(75) }}</posy>
            <width>669</width>
            <height>{{ vscale(669) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>20FFFFFF</colordiffuse>
        </control>
        <control type="image">
            <posx>0</posx>
            <posy>{{ vscale(90) }}</posy>
            <width>639</width>
            <height>{{ vscale(639) }}</height>
            <texture>$INFO[Player.Art(thumb)]</texture>
            <aspectratio>scale</aspectratio>
        </control>
        <control type="label">
            <posx>0</posx>
            <posy>{{ vscale(764) }}</posy>
            <width>639</width>
            <height>{{ vscale(35) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[MusicPlayer.Artist]</label>
        </control>
        <control type="label">
            <posx>0</posx>
            <posy>{{ vscale(799) }}</posy>
            <width>639</width>
            <height>{{ vscale(35) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[MusicPlayer.Album]</label>
        </control>
        <control type="label">
            <posx>0</posx>
            <posy>{{ vscale(834) }}</posy>
            <width>639</width>
            <height>{{ vscale(35) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>[B]$INFO[MusicPlayer.Title][/B]</label>
        </control>
        <control type="label">
            <posx>0</posx>
            <posy>{{ vscale(869) }}</posy>
            <width>639</width>
            <height>{{ vscale(35) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[Player.Time]$INFO[MusicPlayer.Duration, / ]</label>
        </control>
    </control>

    <control type="group" id="100">
        <visible>Integer.IsGreater(Container(101).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
        <defaultcontrol>101</defaultcontrol>
        <posx>819</posx>
        <posy>0</posy>
        <width>1101</width>
        <height>1080</height>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>1101</width>
            <height>1080</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>20000000</colordiffuse>
        </control>
        <control type="list" id="101">
            <posx>0</posx>
            <posy>0</posy>
            <width>1101</width>
            <height>1080</height>
            <onright>152</onright>
            <onleft>411</onleft>
            <scrolltime>200</scrolltime>
            <orientation>vertical</orientation>
            <preloaditems>4</preloaditems>
            <pagecontrol>152</pagecontrol>
            <!-- ITEM LAYOUT ########################################## -->
            <itemlayout height="{{ vscale(100) }}">
                <control type="group">
                    <posx>120</posx>
                    <posy>{{ vscale(24) }}</posy>
                    <control type="label">
                        <visible>!String.IsEqual(ListItem.Property(track.ID),Window(10000).Property(script.plex.track.ID))</visible>
                        <posx>-10</posx>
                        <posy>0</posy>
                        <width>60</width>
                        <height>{{ vscale(100) }}</height>
                        <font>font10</font>
                        <align>center</align>
                        <aligny>center</aligny>
                        <textcolor>D8FFFFFF</textcolor>
                        <label>[B]$INFO[ListItem.Property(track.number)][/B]</label>
                    </control>
                    <control type="image">
                        <visible>String.IsEqual(ListItem.Property(track.ID),Window(10000).Property(script.plex.track.ID))</visible>
                        <posx>2</posx>
                        <posy>{{ vscale(32.5) }}</posy>
                        <width>35</width>
                        <height>{{ vscale(35) }}</height>
                        <texture>script.plex/indicators/playing-circle.png</texture>
                        <colordiffuse>FFE5A00D</colordiffuse>
                    </control>
                    <control type="image">
                        <posx>63</posx>
                        <posy>{{ vscale(11) }}</posy>
                        <width>74</width>
                        <height>{{ vscale(74) }}</height>
                        <texture>$INFO[ListItem.Thumb]</texture>
                        <aspectratio>scale</aspectratio>
                    </control>
                    <control type="group">
                        <posx>168</posx>
                        <posy>0</posy>
                        <control type="label">
                            <posx>0</posx>
                            <posy>{{ vscale(15) }}</posy>
                            <width>723</width>
                            <height>{{ vscale(30) }}</height>
                            <font>font10</font>
                            <align>left</align>
                            <aligny>center</aligny>
                            <textcolor>FFFFFFFF</textcolor>
                            <label>[B]$INFO[ListItem.Label][/B]</label>
                        </control>
                        <control type="label">
                            <posx>0</posx>
                            <posy>{{ vscale(50) }}</posy>
                            <width>723</width>
                            <height>{{ vscale(30) }}</height>
                            <font>font10</font>
                            <align>left</align>
                            <aligny>center</aligny>
                            <textcolor>B8FFFFFF</textcolor>
                            <label>$INFO[ListItem.Label2]</label>
                        </control>
                    </control>
                    <control type="label">
                        <posx>661</posx>
                        <posy>0</posy>
                        <width>200</width>
                        <height>{{ vscale(100) }}</height>
                        <font>font10</font>
                        <align>right</align>
                        <aligny>center</aligny>
                        <textcolor>D8FFFFFF</textcolor>
                        <label>[B]$INFO[ListItem.Property(track.duration)][/B]</label>
                    </control>
                    <control type="image">
                        <visible>String.IsEmpty(ListItem.Property(is.footer))</visible>
                        <posx>0</posx>
                        <posy>{{ vscale(97) }}</posy>
                        <width>861</width>
                        <height>{{ vscale(2) }}</height>
                        <texture>script.plex/white-square.png</texture>
                        <colordiffuse>40000000</colordiffuse>
                    </control>
                </control>
            </itemlayout>

            <!-- FOCUSED LAYOUT ####################################### -->
            <focusedlayout height="{{ vscale(100) }}">
                <control type="group">
                    <control type="group">
                        <visible>!Control.HasFocus(101)</visible>
                        <posx>120</posx>
                        <posy>{{ vscale(24) }}</posy>
                        <control type="label">
                            <visible>!String.IsEqual(ListItem.Property(track.ID),Window(10000).Property(script.plex.track.ID))</visible>
                            <posx>-10</posx>
                            <posy>0</posy>
                            <width>60</width>
                            <height>{{ vscale(100) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <textcolor>D8FFFFFF</textcolor>
                            <label>[B]$INFO[ListItem.Property(track.number)][/B]</label>
                        </control>
                        <control type="image">
                            <visible>String.IsEqual(ListItem.Property(track.ID),Window(10000).Property(script.plex.track.ID))</visible>
                            <posx>0</posx>
                            <posy>{{ vscale(32.5) }}</posy>
                            <width>35</width>
                            <height>{{ vscale(35) }}</height>
                            <texture>script.plex/indicators/playing-circle.png</texture>
                            <colordiffuse>FFE5A00D</colordiffuse>
                        </control>
                        <control type="image">
                            <posx>63</posx>
                            <posy>{{ vscale(11) }}</posy>
                            <width>74</width>
                            <height>{{ vscale(74) }}</height>
                            <texture>$INFO[ListItem.Thumb]</texture>
                            <aspectratio>scale</aspectratio>
                        </control>
                        <control type="group">
                            <posx>168</posx>
                            <posy>0</posy>
                            <control type="label">
                                <posx>0</posx>
                                <posy>{{ vscale(15) }}</posy>
                                <width>723</width>
                                <height>{{ vscale(30) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <aligny>center</aligny>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>[B]$INFO[ListItem.Label][/B]</label>
                            </control>
                            <control type="label">
                                <posx>0</posx>
                                <posy>{{ vscale(50) }}</posy>
                                <width>723</width>
                                <height>{{ vscale(30) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <aligny>center</aligny>
                                <textcolor>B8FFFFFF</textcolor>
                                <label>$INFO[ListItem.Label2]</label>
                            </control>
                        </control>
                        <control type="label">
                            <posx>669</posx>
                            <posy>0</posy>
                            <width>200</width>
                            <height>{{ vscale(100) }}</height>
                            <font>font10</font>
                            <align>right</align>
                            <aligny>center</aligny>
                            <textcolor>D8FFFFFF</textcolor>
                            <label>[B]$INFO[ListItem.Property(track.duration)][/B]</label>
                        </control>
                        <control type="image">
                            <visible>String.IsEmpty(ListItem.Property(is.footer))</visible>
                            <posx>0</posx>
                            <posy>{{ vscale(97) }}</posy>
                            <width>861</width>
                            <height>{{ vscale(2) }}</height>
                            <texture>script.plex/white-square.png</texture>
                            <colordiffuse>40000000</colordiffuse>
                        </control>
                    </control>

                    <control type="group">
                        <visible>Control.HasFocus(101)</visible>
                        <posx>63</posx>
                        <posy>{{ vscale(21) }}</posy>
                        <control type="image">
                            <posx>-40</posx>
                            <posy>{{ vscale(-40) }}</posy>
                            <width>1055</width>
                            <height>{{ vscale(180) }}</height>
                            <texture border="40">script.plex/square-rounded-shadow.png</texture>
                        </control>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>975</width>
                            <height>{{ vscale(100) }}</height>
                            <texture border="12">script.plex/white-square-rounded.png</texture>
                            <colordiffuse>FFE5A00D</colordiffuse>
                        </control>
                        <control type="label">
                            <visible>!String.IsEqual(ListItem.Property(track.ID),Window(10000).Property(script.plex.track.ID))</visible>
                            <posx>24</posx>
                            <posy>0</posy>
                            <width>60</width>
                            <height>{{ vscale(100) }}</height>
                            <font>font12</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <textcolor>B8000000</textcolor>
                            <label>[B]$INFO[ListItem.Property(track.number)][/B]</label>
                        </control>
                        <control type="image">
                            <visible>String.IsEqual(ListItem.Property(track.ID),Window(10000).Property(script.plex.track.ID))</visible>
                            <posx>36</posx>
                            <posy>{{ vscale(32.5) }}</posy>
                            <width>35</width>
                            <height>{{ vscale(35) }}</height>
                            <texture>script.plex/indicators/playing-circle.png</texture>
                            <colordiffuse>FF000000</colordiffuse>
                        </control>
                        <control type="image">
                            <posx>103</posx>
                            <posy>0</posy>
                            <width>100</width>
                            <height>{{ vscale(100) }}</height>
                            <texture>$INFO[ListItem.Thumb]</texture>
                            <aspectratio>scale</aspectratio>
                        </control>
                        <control type="group">
                            <posx>235</posx>
                            <posy>0</posy>
                            <control type="label">
                                <posx>0</posx>
                                <posy>{{ vscale(16) }}</posy>
                                <width>669</width>
                                <height>{{ vscale(30) }}</height>
                                <font>font12</font>
                                <align>left</align>
                                <aligny>center</aligny>
                                <textcolor>DF000000</textcolor>
                                <label>[B]$INFO[ListItem.Label][/B]</label>
                            </control>
                            <control type="label">
                                <posx>0</posx>
                                <posy>{{ vscale(51) }}</posy>
                                <width>669</width>
                                <height>{{ vscale(30) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <aligny>center</aligny>
                                <textcolor>98000000</textcolor>
                                <label>$INFO[ListItem.Label2]</label>
                            </control>
                        </control>
                        <control type="label">
                            <posx>735</posx>
                            <posy>0</posy>
                            <width>200</width>
                            <height>{{ vscale(100) }}</height>
                            <font>font12</font>
                            <align>right</align>
                            <aligny>center</aligny>
                            <textcolor>B8000000</textcolor>
                            <label>[B]$INFO[ListItem.Property(track.duration)][/B]</label>
                        </control>
                    </control>
                </control>

            </focusedlayout>
        </control>

        <control type="scrollbar" id="152">
            <hitrect x="1039" y="33" w="90" h="1014" />
            <left>1059</left>
            <top>33</top>
            <width>12</width>
            <height>1014</height>
            <onleft>101</onleft>
            <visible>true</visible>
            <texturesliderbackground colordiffuse="40000000" border="5">script.plex/white-square-rounded.png</texturesliderbackground>
            <texturesliderbar colordiffuse="77FFFFFF" border="5">script.plex/white-square-rounded.png</texturesliderbar>
            <texturesliderbarfocus colordiffuse="FFE5A00D" border="5">script.plex/white-square-rounded.png</texturesliderbarfocus>
            <textureslidernib>-</textureslidernib>
            <textureslidernibfocus>-</textureslidernibfocus>
            <pulseonselect>false</pulseonselect>
            <orientation>vertical</orientation>
            <showonepage>false</showonepage>
            <onleft>151</onleft>
        </control>
    </control>
</control>

<control type="grouplist" id="400">
    <defaultcontrol>406</defaultcontrol>
    <hitrect x="460" y="998" w="1000" h="55" />
    <posx>0</posx>
    <posy>{{ vscale(116) }}r</posy>
    <width>819</width>

    <height>{{ vscale(124) }}</height>
    <align>center</align>
    <onup>500</onup>
    <onright>100</onright>
    <itemgap>-40</itemgap>
    <orientation>horizontal</orientation>
    <scrolltime tween="quadratic" easing="out">200</scrolltime>
    <usecontrolcoords>false</usecontrolcoords>

    {% include "includes/music_player_buttons.xml.tpl" %}

</control>

<control type="group">
    <posx>0</posx>
    <posy>{{ vscale(140) }}r</posy>
    <control type="button" id="500">
        <enable>Player.HasAudio</enable>
        <hitrect x="0" y="-19" w="819" h="48" />
        <posx>0</posx>
        <posy>0</posy>
        <width>819</width>
        <height>{{ vscale(10) }}</height>
        <onup>100</onup>
        <ondown>400</ondown>
        <texturefocus>script.plex/white-square.png</texturefocus>
        <texturenofocus>script.plex/white-square.png</texturenofocus>
        <colordiffuse>A0000000</colordiffuse>
    </control>
    <control type="image" id="510">
        <visible>Control.HasFocus(500)</visible>
        <animation effect="fade" time="100" delay="100" end="100">Visible</animation>
        <posx>0</posx>
        <posy>1</posy>
        <width>1</width>
        <height>{{ vscale(8) }}</height>
        <texture>script.plex/white-square.png</texture>
        <colordiffuse>FFE5A00D</colordiffuse>
    </control>
    <control type="progress">
        <visible>!Control.HasFocus(500)</visible>
        <description>Progressbar</description>
        <posx>0</posx>
        <posy>2</posy>
        <width>819</width>
        <height>{{ vscale(6) }}</height>
        <texturebg>script.plex/transparent-6px.png</texturebg>
        <lefttexture>-</lefttexture>
        <midtexture colordiffuse="FFCC7B19">script.plex/white-square-6px.png</midtexture>
        <righttexture>-</righttexture>
        <overlaytexture>-</overlaytexture>
        <info>Player.Progress</info>
    </control>
    <control type="progress">
        <visible>Control.HasFocus(500)</visible>
        <description>Progressbar</description>
        <posx>0</posx>
        <posy>2</posy>
        <width>819</width>
        <height>{{ vscale(6) }}</height>
        <texturebg>script.plex/transparent-6px.png</texturebg>
        <lefttexture>-</lefttexture>
        <midtexture colordiffuse="FFAC5B00">script.plex/white-square-6px.png</midtexture>
        <righttexture>-</righttexture>
        <overlaytexture>-</overlaytexture>
        <info>Player.Progress</info>
    </control>
</control>

<!-- <control type="slider">
    <posx>0</posx>
    <posy>{{ vscale(942) }}</posy>
    <width>819</width>
    <height>{{ vscale(6) }}</height>
    <visible>true</visible>
    <texturesliderbar>-</texturesliderbar>
    <textureslidernib colordiffuse="FFE5A00D">script.plex/white-square-6px.png</textureslidernib>
    <textureslidernibfocus>-</textureslidernibfocus>
    <action>seek</action>
</control> -->

<!-- <control type="image" id="201">
    <visible>!Control.HasFocus(100) + !Control.HasFocus(500)</visible>
    <animation effect="fade" time="100" delay="100" end="0">Hidden</animation>
    <posx>0</posx>
    <posy>{{ vscale(942) }}</posy>
    <width>1</width>
    <height>{{ vscale(6) }}</height>
    <texture>script.plex/white-square.png</texture>
    <colordiffuse>FFCC7B19</colordiffuse>
</control> -->

<control type="group" id="202">
    <visible>Control.HasFocus(500) + !String.IsEmpty(Window.Property(time.selection))</visible>
    <posx>0</posx>
    <posy>{{ vscale(184) }}r</posy>
    <control type="group" id="203">
        <posx>-50</posx>
        <posy>0</posy>
        <control type="image">
            <animation effect="fade" time="100" delay="100" end="100">Visible</animation>
            <posx>0</posx>
            <posy>0</posy>
            <width>101</width>
            <height>{{ vscale(39) }}</height>
            <texture>script.plex/indicators/player-selection-time_box.png</texture>
            <colordiffuse>D0000000</colordiffuse>
        </control>
        <control type="label">
            <posx>0</posx>
            <posy>0</posy>
            <width>101</width>
            <height>{{ vscale(40) }}</height>
            <font>font10</font>
            <align>center</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>$INFO[Window.Property(time.selection)]</label>
        </control>
    </control>
    <control type="image">
        <animation effect="fade" time="100" delay="100" end="100">Visible</animation>
        <posx>-6</posx>
        <posy>{{ vscale(39) }}</posy>
        <width>15</width>
        <height>{{ vscale(7) }}</height>
        <texture>script.plex/indicators/player-selection-time_arrow.png</texture>
        <colordiffuse>D0000000</colordiffuse>
    </control>
</control>
{% endblock controls %}