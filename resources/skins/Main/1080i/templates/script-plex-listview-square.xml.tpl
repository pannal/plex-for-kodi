{% extends "library.xml.tpl" %}
{% block header_bg %}{% endblock %}
{% block header_animation %}{% endblock %}
{% block filteropts_grouplist_attrs %} id="600"{% endblock %}
{% block no_content %}{% endblock %}

{% block content %}
    <control type="group">
        <posx>60</posx>
        <posy>{{ vscale(248) }}</posy>
        <control type="group">
            <visible>String.IsEqual(Window.Property(media),photo) | String.IsEqual(Window.Property(media),photodirectory)</visible>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>630</width>
                <height>{{ vscale(355) }}</height>
                <texture colordiffuse="A0000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>630</width>
                <height>{{ vscale(355) }}</height>
                <fadetime>500</fadetime>
                <texture background="true" fallback="script.plex/thumb_fallbacks/photo.png">$INFO[Container(101).ListItem.Thumb]</texture>
                <aspectratio>keep</aspectratio>
            </control>
        </control>
        <control type="image">
            <visible>String.IsEqual(Window.Property(media),artist)</visible>
            <posx>0</posx>
            <posy>0</posy>
            <width>355</width>
            <height>{{ vscale(355) }}</height>
            <fadetime>500</fadetime>
            <texture background="true" fallback="script.plex/thumb_fallbacks/music.png">$INFO[Container(101).ListItem.Thumb]</texture>
            <aspectratio>scale</aspectratio>
        </control>
        <control type="group">
            <visible>!String.IsEmpty(Container(101).ListItem.Label2)</visible>
            <control type="label">
                <posx>0</posx>
                <posy>{{ vscale(355) }}</posy>
                <width>310</width>
                <height>{{ vscale(80) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <label>[B]$INFO[Container(101).ListItem.Label][/B]</label>
            </control>
            <control type="label">
                <posx>630</posx>
                <posy>{{ vscale(355) }}</posy>
                <width>310</width>
                <height>{{ vscale(80) }}</height>
                <font>font12</font>
                <align>right</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <label>[B]$INFO[Container(101).ListItem.Label2][/B]</label>
            </control>
        </control>
        <control type="group">
            <visible>String.IsEmpty(Container(101).ListItem.Label2)</visible>
            <control type="label">
                <posx>0</posx>
                <posy>{{ vscale(355) }}</posy>
                <width>630</width>
                <height>{{ vscale(80) }}</height>
                <font>font12</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <label>[B]$INFO[Container(101).ListItem.Label][/B]</label>
            </control>
        </control>
        <control type="image">
            <posx>0</posx>
            <posy>{{ vscale(435) }}</posy>
            <width>630</width>
            <height>{{ vscale(2) }}</height>
            <texture>script.plex/white-square.png</texture>
            <colordiffuse>40000000</colordiffuse>
        </control>
        <control type="textbox">
            <posx>0</posx>
            <posy>{{ vscale(463) }}</posy>
            <width>630</width>
            <height>{{ vscale(307) }}</height>
            <font>font12</font>
            <align>left</align>
            <textcolor>FFDDDDDD</textcolor>
            <label>$INFO[Container(101).ListItem.Property(camera.model),,[CR]]$INFO[Container(101).ListItem.Property(camera.lens),,[CR]]$INFO[Container(101).ListItem.Property(photo.dims),,[CR]]$INFO[Container(101).ListItem.Property(camera.settings),,[CR]]$INFO[Container(101).ListItem.Property(photo.summary),[CR],[CR]]$INFO[Container(101).ListItem.Property(summary)]</label>
        </control>
    </control>

    <control type="group" id="50">
        <posx>0</posx>
        <posy>{{ vscale(135) }}</posy>
        <defaultcontrol>101</defaultcontrol>

        {% block buttons %}
            <control type="grouplist" id="300">
                <defaultcontrol>301</defaultcontrol>
                <posx>30</posx>
                <posy>{{ vscale(-25) }}</posy>
                <width>1000</width>
                <height>{{ vscale(145) }}</height>
                <onup>200</onup>
                <ondown>101</ondown>
                <onright>101</onright>
                <itemgap>-20</itemgap>
                <orientation>horizontal</orientation>
                <scrolltime tween="quadratic" easing="out">200</scrolltime>
                <usecontrolcoords>true</usecontrolcoords>
                <visible>!String.IsEmpty(Window.Property(initialized))</visible>

                {% with attr = {"width": 126, "height": 100} & template = "includes/themed_button.xml.tpl" & hitrect = {"x": 20, "y": 20, "w": 86, "h": 60} %}
                    {% include template with name="play" & id=301 & visible="String.IsEmpty(Window.Property(disable_playback)) + [!String.IsEqual(Window(10000).Property(script.plex.item.type),collection) | String.IsEqual(Window.Property(media),collection)]" %}
                    {% include template with name="shuffle" & id=302 & visible="String.IsEmpty(Window.Property(disable_playback)) + [!String.IsEqual(Window(10000).Property(script.plex.item.type),collection) | String.IsEqual(Window.Property(media),collection)]" %}
                    {% include template with name="more" & id=303 & visible="String.IsEmpty(Window.Property(disable_playback)) + [String.IsEmpty(Window.Property(no.options)) | Player.HasAudio]" %}
                    {% include template with name="chapters" & id=304 & visible="String.IsEmpty(Window.Property(hide.filteroptions))" %}
                {% endwith %}

            </control>
        {% endblock %}

        <control type="group" id="100">
            <visible>Integer.IsGreater(Container(101).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
            <defaultcontrol>101</defaultcontrol>
            <posx>750</posx>
            <posy>0</posy>
            <width>1170</width>
            <height>1080</height>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>1170</width>
                <height>1080</height>
                <texture>script.plex/white-square.png</texture>
                <colordiffuse>20000000</colordiffuse>
            </control>
            <control type="list" id="101">
                <hitrect x="60" y="0" w="1010" h="945" />
                <posx>0</posx>
                <posy>0</posy>
                <width>1170</width>
                <height>945</height>
                <onup>600</onup>
                <onright>151</onright>
                <onleft>304</onleft>
                <scrolltime>200</scrolltime>
                <orientation>vertical</orientation>
                <preloaditems>4</preloaditems>
                <pagecontrol>152</pagecontrol>
                <!-- ITEM LAYOUT ########################################## -->
                <itemlayout height="{{ vscale(76) }}">
                    <control type="group">
                        <posx>120</posx>
                        <posy>{{ vscale(24) }}</posy>
                        <control type="group">
                            {% include "includes/watched_indicator.xml.tpl" with xoff=915 & yoff=8 & uw_size=35 & uw_posy=-3 & with_count=True & force_nowbg=True & scale="large" & wbg="script.plex/white-square-rounded.png" %}

                            <control type="group">
                                <posx>0</posx>
                                <posy>0</posy>
                                <control type="label">
                                    <visible>String.IsEmpty(ListItem.Property(is.folder))</visible>
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>915</width>
                                    <height>{{ vscale(72) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>[B]$INFO[ListItem.Label][/B]</label>
                                </control>
                                <control type="label">
                                    <visible>!String.IsEmpty(ListItem.Property(is.folder))</visible>
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <width>915</width>
                                    <height>{{ vscale(72) }}</height>
                                    <font>font10</font>
                                    <align>left</align>
                                    <aligny>center</aligny>
                                    <textcolor>FFFFFFFF</textcolor>
                                    <label>[B]$INFO[ListItem.Label][COLOR FFE5A00D]/[/COLOR][/B]</label>
                                </control>
                            </control>
                        </control>
                        <control type="image">
                            <visible>String.IsEmpty(ListItem.Property(is.footer))</visible>
                            <posx>0</posx>
                            <posy>{{ vscale(72) }}</posy>
                            <width>915</width>
                            <height>{{ vscale(2) }}</height>
                            <texture>script.plex/white-square.png</texture>
                            <colordiffuse>40000000</colordiffuse>
                        </control>
                    </control>
                </itemlayout>

                <!-- FOCUSED LAYOUT ####################################### -->
                <focusedlayout height="{{ vscale(76) }}">
                    <control type="group">
                        <control type="group">
                            <visible>!Control.HasFocus(101)</visible>
                            <posx>120</posx>
                            <posy>{{ vscale(24) }}</posy>
                            <control type="group">
                                {% include "includes/watched_indicator.xml.tpl" with xoff=915 & yoff=8 & uw_size=35 & uw_posy=-3 & with_count=True & force_nowbg=True & scale="large" & wbg="script.plex/white-square-rounded.png" %}
                                <control type="group">
                                    <posx>0</posx>
                                    <posy>0</posy>
                                    <control type="group">
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <control type="label">
                                            <visible>String.IsEmpty(ListItem.Property(is.folder))</visible>
                                            <posx>0</posx>
                                            <posy>0</posy>
                                            <width>915</width>
                                            <height>{{ vscale(72) }}</height>
                                            <font>font10</font>
                                            <align>left</align>
                                            <aligny>center</aligny>
                                            <textcolor>FFFFFFFF</textcolor>
                                            <label>[B]$INFO[ListItem.Label][/B]</label>
                                        </control>
                                        <control type="label">
                                            <visible>!String.IsEmpty(ListItem.Property(is.folder))</visible>
                                            <posx>0</posx>
                                            <posy>0</posy>
                                            <width>915</width>
                                            <height>{{ vscale(72) }}</height>
                                            <font>font10</font>
                                            <align>left</align>
                                            <aligny>center</aligny>
                                            <textcolor>FFFFFFFF</textcolor>
                                            <label>[B]$INFO[ListItem.Label][COLOR FFE5A00D]/[/COLOR][/B]</label>
                                        </control>
                                    </control>
                                </control>
                            </control>
                            <control type="image">
                                <visible>String.IsEmpty(ListItem.Property(is.footer))</visible>
                                <posx>0</posx>
                                <posy>{{ vscale(72) }}</posy>
                                <width>915</width>
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
                                <width>1085</width>
                                <height>{{ vscale(156) }}</height>
                                <texture border="40">script.plex/square-rounded-shadow.png</texture>
                            </control>
                            <control type="image">
                                <posx>0</posx>
                                <posy>0</posy>
                                <width>1005</width>
                                <height>{{ vscale(76) }}</height>
                                <texture border="12">script.plex/white-square-rounded.png</texture>
                                <colordiffuse>FFE5A00D</colordiffuse>
                            </control>

                            <control type="group">
                                {% include "includes/watched_indicator.xml.tpl" with xoff=973 & yoff=12 & uw_size=35 & with_count=True & force_nowbg=True & scale="large" & wbg="script.plex/white-square-rounded.png" %}
                                <control type="group">
                                    <posx>60</posx>
                                    <posy>0</posy>
                                    <control type="label">
                                        <visible>String.IsEmpty(ListItem.Property(is.folder))</visible>
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>885</width>
                                        <height>{{ vscale(72) }}</height>
                                        <font>font12</font>
                                        <align>left</align>
                                        <aligny>center</aligny>
                                        <textcolor>DF000000</textcolor>
                                        <label>[B]$INFO[ListItem.Label][/B]</label>
                                    </control>
                                    <control type="label">
                                        <visible>!String.IsEmpty(ListItem.Property(is.folder))</visible>
                                        <posx>0</posx>
                                        <posy>0</posy>
                                        <width>885</width>
                                        <height>{{ vscale(72) }}</height>
                                        <font>font10</font>
                                        <align>left</align>
                                        <aligny>center</aligny>
                                        <textcolor>FF000000</textcolor>
                                        <label>[B]$INFO[ListItem.Label]/[/B]</label>
                                    </control>
                                </control>
                            </control>
                        </control>
                    </control>
                </focusedlayout>
            </control>

            <control type="scrollbar" id="152">
                <hitrect x="1108" y="33" w="90" h="879" />
                <left>1128</left>
                <top>33</top>
                <width>12</width>
                <height>879</height>
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

    <control type="group" id="150">
        <visible>String.IsEqual(Window(10000).Property(script.plex.sort),titleSort) + Integer.IsGreater(Container(101).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
        <defaultcontrol>151</defaultcontrol>
        <posx>1830</posx>
        <posy>{{ vscale(135) + 33 }}</posy>
        <width>20</width>
        <height>920</height>
        <control type="list" id="151">
            <posx>0</posx>
            <posy>0</posy>
            <width>34</width>
            <height>1050</height>
            <onleft>100</onleft>
            <onright>152</onright>
            <scrolltime>200</scrolltime>
            <orientation>vertical</orientation>
            <!-- ITEM LAYOUT ########################################## -->
            <itemlayout height="34">
                <control type="group">
                    <posx>0</posx>
                    <posy>0</posy>
                    <control type="group">
                        <posx>0</posx>
                        <posy>0</posy>
                        <control type="label">
                            <visible>!String.IsEqual(Window(10000).Property(script.plex.key), ListItem.Property(letter))</visible>
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>34</width>
                            <height>{{ vscale(32) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <textcolor>99FFFFFF</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <visible>String.IsEqual(Window(10000).Property(script.plex.key), ListItem.Property(key))</visible>
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>34</width>
                            <height>{{ vscale(32) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <textcolor>FFE5A00D</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </control>
                </control>
            </itemlayout>

            <!-- FOCUSED LAYOUT ####################################### -->
            <focusedlayout height="34">
                <control type="group">
                    <posx>0</posx>
                    <posy>0</posy>
                    <control type="group">
                        <posx>0</posx>
                        <posy>0</posy>
                        <control type="label">
                            <visible>!String.IsEqual(Window(10000).Property(script.plex.key), ListItem.Property(letter))</visible>
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>34</width>
                            <height>{{ vscale(32) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <textcolor>99FFFFFF</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                        <control type="label">
                            <visible>String.IsEqual(Window(10000).Property(script.plex.key), ListItem.Property(key))</visible>
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>34</width>
                            <height>{{ vscale(32) }}</height>
                            <font>font10</font>
                            <align>center</align>
                            <aligny>center</aligny>
                            <textcolor>FFE5A00D</textcolor>
                            <label>$INFO[ListItem.Label]</label>
                        </control>
                    </control>

                    <control type="group">
                        <visible>Control.HasFocus(151)</visible>
                        <posx>0</posx>
                        <posy>0</posy>
                        <control type="image">
                            <visible>Control.HasFocus(151)</visible>
                            <posx>0</posx>
                            <posy>0</posy>
                            <width>34</width>
                            <height>{{ vscale(34) }}</height>
                            <colordiffuse>FFE5A00D</colordiffuse>
                            <texture border="12">script.plex/white-outline-rounded.png</texture>
                        </control>
                    </control>
                </control>
            </focusedlayout>
        </control>
    </control>
{% endblock content %}