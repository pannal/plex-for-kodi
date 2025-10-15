{% extends "base.xml.tpl" %}
{% block headers %}<defaultcontrol>100</defaultcontrol>{% endblock %}
{% block controls %}
<control type="group">
    <control type="group" id="100">
        <!-- <visible>Integer.IsGreater(Container(101).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible> -->
        <defaultcontrol>101</defaultcontrol>
        <posx>750</posx>
        <posy>{{ vscale(140) }}</posy>
        <width>1170</width>
        <height>{{ vscale(800) }}</height>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>1170</width>
            <height>{{ vscale(800) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>B3111111</colordiffuse>
        </control>
        <control type="list" id="101">
            <posx>0</posx>
            <posy>0</posy>
            <width>1170</width>
            <height>{{ vscale(800) }}</height>
            <onright>152</onright>
            <scrolltime>200</scrolltime>
            <orientation>vertical</orientation>
            <preloaditems>4</preloaditems>
            <pagecontrol>152</pagecontrol>
            <!-- ITEM LAYOUT ########################################## -->
            <itemlayout height="{{ vscale(101) }}">
                <control type="group">
                    <posx>120</posx>
                    <posy>{{ vscale(24) }}</posy>
                    <control type="label">
                        <visible>String.IsEmpty(ListItem.Property(playing))</visible>
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
                        <visible>!String.IsEmpty(ListItem.Property(playing))</visible>
                        <posx>2</posx>
                        <posy>{{ vscale(32.5) }}</posy>
                        <width>35</width>
                        <height>{{ vscale(35) }}</height>
                        <texture>script.plex/indicators/playing-circle.png</texture>
                        <colordiffuse>FFE5A00D</colordiffuse>
                    </control>
                    <control type="group">
                        <visible>String.IsEmpty(ListItem.Property(video))</visible>
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
                                <width>692</width>
                                <height>{{ vscale(30) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <aligny>center</aligny>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>[B]$INFO[ListItem.Label][/B]</label>
                                <scroll>true</scroll>
                            </control>
                            <control type="label">
                                <posx>0</posx>
                                <posy>{{ vscale(50) }}</posy>
                                <width>692</width>
                                <height>{{ vscale(30) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <aligny>center</aligny>
                                <textcolor>B8FFFFFF</textcolor>
                                <label>$INFO[ListItem.Label2]</label>
                                <scroll>true</scroll>
                            </control>
                        </control>
                    </control>
                    <control type="group">
                        <visible>!String.IsEmpty(ListItem.Property(video))</visible>
                        <control type="image">
                            <posx>63</posx>
                            <posy>{{ vscale(11) }}</posy>
                            <width>132</width>
                            <height>{{ vscale(74) }}</height>
                            <texture>$INFO[ListItem.Thumb]</texture>
                            <aspectratio>scale</aspectratio>
                        </control>
                        <control type="group">
                            <visible>!String.IsEmpty(ListItem.Property(progress))</visible>
                            <posx>63</posx>
                            <posy>{{ vscale(79) }}</posy>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>132</width>
                                <height>{{ vscale(6) }}</height>
                                <texture>script.plex/white-square.png</texture>
                                <colordiffuse>C0000000</colordiffuse>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>1</posy>
                                <width>132</width>
                                <height>{{ vscale(4) }}</height>
                                <texture>$INFO[ListItem.Property(progress)]</texture>
                                <colordiffuse>FFCC7B19</colordiffuse>
                            </control>
                        </control>
                        {% include "includes/watched_indicator.xml.tpl" with xoff=132+63 & yoff=11 & uw_posy=11 & uw_size=24 & scale="tiny" %}
                        <control type="group">
                            <posx>226</posx>
                            <posy>0</posy>
                            <control type="label">
                                <posx>0</posx>
                                <posy>{{ vscale(15) }}</posy>
                                <width>584</width>
                                <height>{{ vscale(30) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <aligny>center</aligny>
                                <textcolor>FFFFFFFF</textcolor>
                                <label>[B]$INFO[ListItem.Label][/B]</label>
                                <scroll>true</scroll>
                            </control>
                            <control type="label">
                                <posx>0</posx>
                                <posy>{{ vscale(50) }}</posy>
                                <width>584</width>
                                <height>{{ vscale(30) }}</height>
                                <font>font10</font>
                                <align>left</align>
                                <aligny>center</aligny>
                                <textcolor>B8FFFFFF</textcolor>
                                <label>$INFO[ListItem.Label2]</label>
                                <scroll>true</scroll>
                            </control>
                        </control>
                    </control>
                    <control type="label">
                        <posx>730</posx>
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
                        <posy>{{ vscale(98) }}</posy>
                        <width>930</width>
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
                            <visible>String.IsEmpty(ListItem.Property(playing))</visible>
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
                            <visible>!String.IsEmpty(ListItem.Property(playing))</visible>
                            <posx>0</posx>
                            <posy>{{ vscale(32.5) }}</posy>
                            <width>35</width>
                            <height>{{ vscale(35) }}</height>
                            <texture>script.plex/indicators/playing-circle.png</texture>
                            <colordiffuse>FFE5A00D</colordiffuse>
                        </control>
                        <control type="group">
                            <visible>String.IsEmpty(ListItem.Property(video))</visible>
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
                                    <width>692</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>[B]$INFO[ListItem.Label][/B]</label>
                                    <scroll>true</scroll>
                                </control>
                                <control type="label">
                                    <posx>0</posx>
                                    <posy>{{ vscale(50) }}</posy>
                                    <width>692</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>B8FFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label2]</label>
                                    <scroll>true</scroll>
                                </control>
                            </control>
                        </control>
                        <control type="group">
                            <visible>!String.IsEmpty(ListItem.Property(video))</visible>
                            <control type="image">
                                <posx>63</posx>
                                <posy>{{ vscale(11) }}</posy>
                                <width>132</width>
                                <height>{{ vscale(74) }}</height>
                                <texture>$INFO[ListItem.Thumb]</texture>
                                <aspectratio>scale</aspectratio>
                            </control>
                            {% include "includes/watched_indicator.xml.tpl" with xoff=132+63 & yoff=11 & uw_posy=11 & uw_size=24 & scale="tiny" %}
                            <control type="group">
                                <posx>226</posx>
                                <posy>0</posy>
                                <control type="label">
                                    <posx>0</posx>
                                    <posy>{{ vscale(15) }}</posy>
                                    <width>584</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>[B]$INFO[ListItem.Label][/B]</label>
                                    <scroll>true</scroll>
                                </control>
                                <control type="label">
                                    <posx>0</posx>
                                    <posy>{{ vscale(50) }}</posy>
                                    <width>584</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>B8FFFFFF</textcolor>
                                    <label>$INFO[ListItem.Label2]</label>
                                    <scroll>true</scroll>
                                </control>
                            </control>
                        </control>
                        <control type="label">
                            <posx>756</posx>
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
                            <width>930</width>
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
                            <width>1124</width>
                            <height>{{ vscale(180) }}</height>
                            <texture border="40">script.plex/square-rounded-shadow.png</texture>
                        </control>
                        <control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>1044</width>
                            <height>{{ vscale(100) }}</height>
                            <texture border="12">script.plex/white-square-rounded.png</texture>
                            <colordiffuse>FFE5A00D</colordiffuse>
                        </control>
                        <!-- comment the previous and uncomment the following for re-enabling options button -->
                        <!--<control type="image">
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>999</width>
                            <height>{{ vscale(100) }}</height>
                            <texture border="12">script.plex/white-square-left-rounded.png</texture>
                            <colordiffuse>FFE5A00D</colordiffuse>
                        </control>
                        <control type="image">
                            <posx>999</posx>
                            <posy>0</posy>
                            <width>45</width>
                            <height>{{ vscale(100) }}</height>
                            <texture>script.plex/buttons/more-vertical.png</texture>
                            <colordiffuse>99FFFFFF</colordiffuse>
                        </control>-->
                        <control type="label">
                            <visible>String.IsEmpty(ListItem.Property(playing))</visible>
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
                            <visible>!String.IsEmpty(ListItem.Property(playing))</visible>
                            <posx>36</posx>
                            <posy>{{ vscale(32.5) }}</posy>
                            <width>35</width>
                            <height>{{ vscale(35) }}</height>
                            <texture>script.plex/indicators/playing-circle.png</texture>
                            <colordiffuse>FF000000</colordiffuse>
                        </control>
                        <control type="group">
                            <visible>String.IsEmpty(ListItem.Property(video))</visible>
                            <control type="image">
                                <visible>String.IsEmpty(ListItem.Property(video))</visible>
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
                                    <width>638</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font12</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>DF000000</textcolor>
                                    <label>[B]$INFO[ListItem.Label][/B]</label>
                                    <scroll>true</scroll>
                                </control>
                                <control type="label">
                                    <posx>0</posx>
                                    <posy>{{ vscale(51) }}</posy>
                                    <width>638</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>98000000</textcolor>
                                    <label>$INFO[ListItem.Label2]</label>
                                    <scroll>true</scroll>
                                </control>
                            </control>
                        </control>
                        <control type="group">
                            <visible>!String.IsEmpty(ListItem.Property(video))</visible>
                            <control type="image">
                                <posx>103</posx>
                                <posy>0</posy>
                                <width>178</width>
                                <height>{{ vscale(100) }}</height>
                                <texture>$INFO[ListItem.Thumb]</texture>
                                <aspectratio>scale</aspectratio>
                            </control>
                            <control type="group">
                                <visible>!String.IsEmpty(ListItem.Property(progress))</visible>
                                <posx>103</posx>
                                <posy>{{ vscale(94) }}</posy>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>178</width>
                                    <height>{{ vscale(6) }}</height>
                                    <texture>script.plex/white-square.png</texture>
                                    <colordiffuse>C0000000</colordiffuse>
                                </control>
                                <control type="image">
                                    <posx>0</posx>
                                    <posy>1</posy>
                                    <width>178</width>
                                    <height>{{ vscale(4) }}</height>
                                    <texture>$INFO[ListItem.Property(progress)]</texture>
                                    <colordiffuse>FFCC7B19</colordiffuse>
                                </control>
                            </control>
                            {% include "includes/watched_indicator.xml.tpl" with xoff=178+103 %}
                            <control type="group">
                                <posx>313</posx>
                                <posy>0</posy>
                                <control type="label">
                                    <posx>0</posx>
                                    <posy>{{ vscale(16) }}</posy>
                                    <width>510</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font12</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>DF000000</textcolor>
                                    <label>[B]$INFO[ListItem.Label][/B]</label>
                                    <scroll>true</scroll>
                                </control>
                                <control type="label">
                                    <posx>0</posx>
                                    <posy>{{ vscale(51) }}</posy>
                                    <width>510</width>
                                    <height>{{ vscale(30) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>98000000</textcolor>
                                    <label>$INFO[ListItem.Label2]</label>
                                    <scroll>true</scroll>
                                </control>
                            </control>
                        </control>
                        <control type="label">
                            <posx>802</posx>
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
            <hitrect x="1108" y="33" w="90" h="734" />
            <left>1128</left>
            <top>33</top>
            <width>10</width>
            <height>{{ vscale(734) }}</height>
            <visible>true</visible>
            <texturesliderbackground colordiffuse="40000000" border="5">script.plex/white-square-rounded.png</texturesliderbackground>
            <texturesliderbar colordiffuse="77FFFFFF" border="5">script.plex/white-square-rounded.png</texturesliderbar>
            <texturesliderbarfocus colordiffuse="FFE5A00D" border="5">script.plex/white-square-rounded.png</texturesliderbarfocus>
            <textureslidernib>-</textureslidernib>
            <textureslidernibfocus>-</textureslidernibfocus>
            <pulseonselect>false</pulseonselect>
            <orientation>vertical</orientation>
            <showonepage>false</showonepage>
        </control>
    </control>
</control>
{% endblock controls %}