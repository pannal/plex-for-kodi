{% extends "base.xml.tpl" %}
{% block headers %}<onload>SetProperty(dropdown,1)</onload>{% endblock %}
{% block backgroundcolor %}{% endblock %}
{% block controls %}
<!-- BACKGROUNDS -->
<control type="group">
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>564</width>
        <height>1080</height>
        <texture colordiffuse="4C000000">script.plex/white-square.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>{{ vscale(135) }}</posy>
        <width>564</width>
        <height>{{ vscale(810) }}</height>
        <visible>String.IsEmpty(Window.Property(hide.kbd))</visible>
        <texture colordiffuse="FF2D2D2D">script.plex/white-square.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>{{ vscale(135) }}</posy>
        <width>564</width>
        <height>{{ vscale(248) }}</height>
        <visible>!String.IsEmpty(Window.Property(hide.kbd))</visible>
        <texture colordiffuse="FF2D2D2D">script.plex/white-square.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>{{ vscale(945) }}</posy>
        <width>564</width>
        <height>{{ vscale(135) }}</height>
        <visible>String.IsEmpty(Window.Property(hide.kbd))</visible>
        <texture colordiffuse="66000000">script.plex/white-square.png</texture>
    </control>
    <control type="image">
        <posx>0</posx>
        <posy>{{ vscale(383) }}</posy>
        <width>564</width>
        <height>{{ vscale(697) }}</height>
        <visible>!String.IsEmpty(Window.Property(hide.kbd))</visible>
        <texture colordiffuse="66000000">script.plex/white-square.png</texture>
    </control>
</control>

<control type="button" id="999">
    <animation effect="zoom" start="100" end="144" time="100" center="80,{{ vscale(67.5) }}" reversible="false">Focus</animation>
    <animation effect="zoom" start="144" end="100" time="100" center="80,{{ vscale(67.5) }}" reversible="false">UnFocus</animation>
    <posx>60</posx>
    <posy>{{ vscale(47.5) }}</posy>
    <width>40</width>
    <height>{{ vscale(40) }}</height>
    <ondown>900</ondown>
    <font>font12</font>
    <focusedcolor>FF000000</focusedcolor>
    <texturefocus colordiffuse="FFE5A00D">script.plex/buttons/search-focus.png</texturefocus>
    <texturenofocus colordiffuse="FFCC7B19">script.plex/buttons/search.png</texturenofocus>
    <onclick>Close</onclick>
    <label> </label>
</control>
<control type="label">
    <scroll>false</scroll>
    <posx>160</posx>
    <posy>{{ vscale(35) }}</posy>
    <width>500</width>
    <height>{{ vscale(65) }}</height>
    <font>font12</font>
    <align>left</align>
    <aligny>center</aligny>
    <textcolor>FFFFFFFF</textcolor>
    <label>[UPPERCASE]$ADDON[script.plexmod 32431][/UPPERCASE]</label>
</control>

<control type="group" id="899">
    <!-- SECTIONS -->
    <control type="group">
        <posx>60</posx>
        <posy>{{ vscale(186) }}</posy>
        <width>459</width>
        <height>{{ vscale(60) }}</height>

        <control type="group">
            <posx>0</posx>
            <posy>0</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>151</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="group">
                <visible>String.IsEqual(Window.Property(search.section),all)</visible>
                <control type="image">
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>151</width>
                    <height>{{ vscale(60) }}</height>
                    <texture colordiffuse="FFCC7B19">script.plex/white-square.png</texture>
                </control>
                <control type="label">
                    <scroll>false</scroll>
                    <posx>0</posx>
                    <posy>0</posy>
                    <width>151</width>
                    <height>{{ vscale(60) }}</height>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <textcolor>FF000000</textcolor>
                    <label>All</label>
                </control>
            </control>
            <control type="label">
                <scroll>false</scroll>
                <visible>!String.IsEqual(Window.Property(search.section),all)</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>151</width>
                <height>{{ vscale(60) }}</height>
                <font>font12</font>
                <align>center</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <label>$ADDON[script.plexmod 32345]</label>
            </control>
        </control>
        <control type="group">
            <posx>154</posx>
            <posy>0</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <visible>String.IsEqual(Window.Property(search.section),movie)</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FFCC7B19">script.plex/white-square.png</texture>
            </control>
        </control>
        <control type="group">
            <posx>231</posx>
            <posy>0</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <visible>String.IsEqual(Window.Property(search.section),show)</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FFCC7B19">script.plex/white-square.png</texture>
            </control>
        </control>
        <control type="group">
            <posx>308</posx>
            <posy>0</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <visible>String.IsEqual(Window.Property(search.section),artist)</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FFCC7B19">script.plex/white-square.png</texture>
            </control>
        </control>
        <control type="group">
            <posx>384</posx>
            <posy>0</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <visible>String.IsEqual(Window.Property(search.section),photo)</visible>
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <texture colordiffuse="FFCC7B19">script.plex/white-square.png</texture>
            </control>
        </control>

        <control type="group" id="900">
            <defaultcontrol>901</defaultcontrol>
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="button" id="901">
                    <hitrect x="0" y="0" w="151" h="60" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>231</width>
                    <height>{{ vscale(140) }}</height>
                    <onright>902</onright>
                    <onup>999</onup>
                    <ondown>650</ondown>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>

                    <texturefocus>-</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label> </label>
                </control>
            </control>
            <control type="group">
                <posx>154</posx>
                <posy>0</posy>
                <control type="button" id="902">
                    <hitrect x="0" y="0" w="74" h="60" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(140) }}</height>
                    <onleft>901</onleft>
                    <onright>903</onright>
                    <onup>999</onup>
                    <ondown>650</ondown>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus>-</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label> </label>
                </control>
            </control>
            <control type="group">
                <posx>231</posx>
                <posy>0</posy>
                <control type="button" id="903">
                    <hitrect x="0" y="0" w="74" h="60" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(140) }}</height>
                    <onleft>902</onleft>
                    <onright>904</onright>
                    <onup>999</onup>
                    <ondown>650</ondown>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus>-</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label> </label>
                </control>
            </control>
            <control type="group">
                <posx>308</posx>
                <posy>0</posy>
                <control type="button" id="904">
                    <hitrect x="0" y="0" w="74" h="60" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(140) }}</height>
                    <onleft>903</onleft>
                    <onright>905</onright>
                    <onup>999</onup>
                    <ondown>650</ondown>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus>-</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label> </label>
                </control>
            </control>
            <control type="group">
                <posx>385</posx>
                <posy>0</posy>
                <control type="button" id="905">
                    <hitrect x="0" y="0" w="74" h="60" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(140) }}</height>
                    <onleft>904</onleft>
                    <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
                    <onup>999</onup>
                    <ondown>650</ondown>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus>-</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label> </label>
                </control>
            </control>
        </control>

        <control type="group">
            <posx>154</posx>
            <posy>0</posy>
            <control type="group">
                <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(30) }}" reversible="true" condition="Control.HasFocus(902)">Conditional</animation>
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <control type="image">
                    <posx>26</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>22</width>
                    <height>{{ vscale(20) }}</height>
                    <texture colordiffuse="FFFFFFFF">script.plex/home/type/movie.png</texture>
                </control>
            </control>
        </control>
        <control type="group">
            <posx>231</posx>
            <posy>0</posy>
            <control type="group">
                <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(30) }}" reversible="true" condition="Control.HasFocus(903)">Conditional</animation>
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <control type="image">
                    <posx>26</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>24</width>
                    <height>{{ vscale(20) }}</height>
                    <texture colordiffuse="FFFFFFFF">script.plex/home/type/show.png</texture>
                </control>
            </control>
        </control>
        <control type="group">
            <posx>308</posx>
            <posy>0</posy>
            <control type="group">
                <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(30) }}" reversible="true" condition="Control.HasFocus(904)">Conditional</animation>
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <control type="image">
                    <posx>26</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>18</width>
                    <height>{{ vscale(20) }}</height>
                    <texture colordiffuse="FFFFFFFF">script.plex/home/type/artist.png</texture>
                </control>
            </control>
        </control>
        <control type="group">
            <posx>385</posx>
            <posy>0</posy>
            <control type="group">
                <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(30) }}" reversible="true" condition="Control.HasFocus(905)">Conditional</animation>
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(60) }}</height>
                <control type="image">
                    <posx>26</posx>
                    <posy>{{ vscale(20) }}</posy>
                    <width>22</width>
                    <height>{{ vscale(20) }}</height>
                    <texture colordiffuse="FFFFFFFF">script.plex/home/type/photo.png</texture>
                </control>
            </control>
        </control>
    </control>

    <!-- ENTRY -->
    <control type="group">
        <posx>60</posx>
        <posy>{{ vscale(276) }}</posy>
        <width>459</width>
        <height>{{ vscale(60) }}</height>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>459</width>
            <height>{{ vscale(60) }}</height>
            <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
        </control>
        <control type="edit" id="650">
            <posx>0</posx>
            <posy>0</posy>
            <width>459</width>
            <height>{{ vscale(60) }}</height>
            <align>left</align>
            <aligny>center</aligny>
            <onup>900</onup>
            <ondown>1001</ondown>
            <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
            <textcolor>00000000</textcolor>
            <label> </label>
            <hinttext> </hinttext>
            <font>font13</font>
            <textoffsetx>30</textoffsetx>
            <texturefocus border="10">script.plex/home/selected.png</texturefocus>
            <texturenofocus>-</texturenofocus>
            <pulseonselect>no</pulseonselect>
        </control>
        <control type="label" id="651">
            <scroll>false</scroll>
            <posx>30</posx>
            <posy>0</posy>
            <width>399</width>
            <height>{{ vscale(60) }}</height>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <font>font13</font>
            <label> </label>
        </control>
    </control>

    <!-- KEYBOARD -->
    <control type="group">
        <posx>60</posx>
        <posy>{{ vscale(360) }}</posy>
        <width>459</width>
        <height>{{ vscale(439) }}</height>
        <visible>String.IsEmpty(Window.Property(hide.kbd))</visible>

        <!-- IMAGES ROW 1 -->
        <control type="group">
            <posx>0</posx>
            <posy>0</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>77</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>154</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>231</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>308</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>385</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
        </control>
        <!-- IMAGES ROW 2 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(77) }}</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>77</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>154</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>231</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>308</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>385</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
        </control>
        <!-- IMAGES ROW 3 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(154) }}</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>77</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>154</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>231</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>308</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>385</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
        </control>
        <!-- IMAGES ROW 4 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(231) }}</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>77</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>154</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>231</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>308</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>385</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
        </control>
        <!-- IMAGES ROW 5 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(308) }}</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>77</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF1F1F1F">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>154</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>231</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>308</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>385</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
        </control>
        <!-- IMAGES ROW 6 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(385) }}</posy>
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>77</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>154</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>231</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>308</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
            <control type="image">
                <posx>385</posx>
                <posy>0</posy>
                <width>74</width>
                <height>{{ vscale(74) }}</height>
                <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
            </control>
        </control>

        <!-- BUTTONS ROW 1 -->
        <control type="group">
            <posx>0</posx>
            <posy>0</posy>
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="button" id="1001">
                    <visible allowhiddenfocus="true">true</visible>
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>650</onup>
                    <ondown>1007</ondown>
                    <onright>1002</onright>
                    <onleft>1006</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>A</label>
                </control>
            </control>
            <control type="group">
                <posx>77</posx>
                <posy>0</posy>
                <control type="button" id="1002">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>650</onup>
                    <ondown>1008</ondown>
                    <onright>1003</onright>
                    <onleft>1001</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>B</label>
                </control>
            </control>
            <control type="group">
                <posx>154</posx>
                <posy>0</posy>
                <control type="button" id="1003">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>650</onup>
                    <ondown>1009</ondown>
                    <onright>1004</onright>
                    <onleft>1002</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>C</label>
                </control>
            </control>
            <control type="group">
                <posx>231</posx>
                <posy>0</posy>
                <control type="button" id="1004">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>650</onup>
                    <ondown>1010</ondown>
                    <onright>1005</onright>
                    <onleft>1003</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>D</label>
                </control>
            </control>
            <control type="group">
                <posx>308</posx>
                <posy>0</posy>
                <control type="button" id="1005">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>650</onup>
                    <ondown>1011</ondown>
                    <onright>1006</onright>
                    <onleft>1004</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>E</label>
                </control>
            </control>
            <control type="group">
                <posx>385</posx>
                <posy>0</posy>
                <control type="button" id="1006">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>650</onup>
                    <ondown>1012</ondown>
                    <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
                    <onleft>1005</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>F</label>
                </control>
            </control>
        </control>
        <!-- BUTTONS ROW 2 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(77) }}</posy>
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="button" id="1007">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1001</onup>
                    <ondown>1013</ondown>
                    <onright>1008</onright>
                    <onleft>1012</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>G</label>
                </control>
            </control>
            <control type="group">
                <posx>77</posx>
                <posy>0</posy>
                <control type="button" id="1008">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1002</onup>
                    <ondown>1014</ondown>
                    <onright>1009</onright>
                    <onleft>1007</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>H</label>
                </control>
            </control>
            <control type="group">
                <posx>154</posx>
                <posy>0</posy>
                <control type="button" id="1009">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1003</onup>
                    <ondown>1015</ondown>
                    <onright>1010</onright>
                    <onleft>1008</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>I</label>
                </control>
            </control>
            <control type="group">
                <posx>231</posx>
                <posy>0</posy>
                <control type="button" id="1010">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1004</onup>
                    <ondown>1016</ondown>
                    <onright>1011</onright>
                    <onleft>1009</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>J</label>
                </control>
            </control>
            <control type="group">
                <posx>308</posx>
                <posy>0</posy>
                <control type="button" id="1011">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1005</onup>
                    <ondown>1017</ondown>
                    <onright>1012</onright>
                    <onleft>1010</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>K</label>
                </control>
            </control>
            <control type="group">
                <posx>385</posx>
                <posy>0</posy>
                <control type="button" id="1012">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1006</onup>
                    <ondown>1018</ondown>
                    <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
                    <onleft>1011</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>L</label>
                </control>
            </control>
        </control>
        <!-- BUTTONS ROW 3 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(154) }}</posy>
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="button" id="1013">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1007</onup>
                    <ondown>1019</ondown>
                    <onright>1014</onright>
                    <onleft>1018</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>M</label>
                </control>
            </control>
            <control type="group">
                <posx>77</posx>
                <posy>0</posy>
                <control type="button" id="1014">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1008</onup>
                    <ondown>1020</ondown>
                    <onright>1015</onright>
                    <onleft>1013</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>N</label>
                </control>
            </control>
            <control type="group">
                <posx>154</posx>
                <posy>0</posy>
                <control type="button" id="1015">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1009</onup>
                    <ondown>1021</ondown>
                    <onright>1016</onright>
                    <onleft>1014</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>O</label>
                </control>
            </control>
            <control type="group">
                <posx>231</posx>
                <posy>0</posy>
                <control type="button" id="1016">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1010</onup>
                    <ondown>1022</ondown>
                    <onright>1017</onright>
                    <onleft>1015</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>P</label>
                </control>
            </control>
            <control type="group">
                <posx>308</posx>
                <posy>0</posy>
                <control type="button" id="1017">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1011</onup>
                    <ondown>1023</ondown>
                    <onright>1018</onright>
                    <onleft>1016</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>Q</label>
                </control>
            </control>
            <control type="group">
                <posx>385</posx>
                <posy>0</posy>
                <control type="button" id="1018">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1012</onup>
                    <ondown>1024</ondown>
                    <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
                    <onleft>1017</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>R</label>
                </control>
            </control>
        </control>
        <!-- BUTTONS ROW 4 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(231) }}</posy>
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="button" id="1019">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1013</onup>
                    <ondown>1025</ondown>
                    <onright>1020</onright>
                    <onleft>1024</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>S</label>
                </control>
            </control>
            <control type="group">
                <posx>77</posx>
                <posy>0</posy>
                <control type="button" id="1020">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1014</onup>
                    <ondown>1026</ondown>
                    <onright>1021</onright>
                    <onleft>1019</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>T</label>
                </control>
            </control>
            <control type="group">
                <posx>154</posx>
                <posy>0</posy>
                <control type="button" id="1021">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1015</onup>
                    <ondown>1027</ondown>
                    <onright>1022</onright>
                    <onleft>1020</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>U</label>
                </control>
            </control>
            <control type="group">
                <posx>231</posx>
                <posy>0</posy>
                <control type="button" id="1022">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1016</onup>
                    <ondown>1028</ondown>
                    <onright>1023</onright>
                    <onleft>1021</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>V</label>
                </control>
            </control>
            <control type="group">
                <posx>308</posx>
                <posy>0</posy>
                <control type="button" id="1023">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1017</onup>
                    <ondown>1029</ondown>
                    <onright>1024</onright>
                    <onleft>1022</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>W</label>
                </control>
            </control>
            <control type="group">
                <posx>385</posx>
                <posy>0</posy>
                <control type="button" id="1024">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1018</onup>
                    <ondown>1030</ondown>
                    <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
                    <onleft>1023</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>X</label>
                </control>
            </control>
        </control>
        <!-- BUTTONS ROW 5 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(308) }}</posy>
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="button" id="1025">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1019</onup>
                    <ondown>1031</ondown>
                    <onright>1026</onright>
                    <onleft>1030</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>Y</label>
                </control>
            </control>
            <control type="group">
                <posx>77</posx>
                <posy>0</posy>
                <control type="button" id="1026">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1020</onup>
                    <ondown>1032</ondown>
                    <onright>1027</onright>
                    <onleft>1025</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>Z</label>
                </control>
            </control>
            <control type="group">
                <posx>154</posx>
                <posy>0</posy>
                <control type="button" id="1027">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1021</onup>
                    <ondown>1033</ondown>
                    <onright>1028</onright>
                    <onleft>1026</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>0[B][/B]</label>
                </control>
            </control>
            <control type="group">
                <posx>231</posx>
                <posy>0</posy>
                <control type="button" id="1028">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1022</onup>
                    <ondown>1034</ondown>
                    <onright>1029</onright>
                    <onleft>1027</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>1[B][/B]</label>
                </control>
            </control>
            <control type="group">
                <posx>308</posx>
                <posy>0</posy>
                <control type="button" id="1029">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1023</onup>
                    <ondown>1035</ondown>
                    <onright>1030</onright>
                    <onleft>1028</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>2[B][/B]</label>
                </control>
            </control>
            <control type="group">
                <posx>385</posx>
                <posy>0</posy>
                <control type="button" id="1030">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1024</onup>
                    <ondown>1036</ondown>
                    <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
                    <onleft>1029</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>3[B][/B]</label>
                </control>
            </control>
        </control>
        <!-- BUTTONS ROW 6 -->
        <control type="group">
            <posx>0</posx>
            <posy>{{ vscale(385) }}</posy>
            <control type="group">
                <posx>0</posx>
                <posy>0</posy>
                <control type="button" id="1031">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1025</onup>
                    <ondown>951</ondown>
                    <onright>1032</onright>
                    <onleft>1036</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>4[B][/B]</label>
                </control>
            </control>
            <control type="group">
                <posx>77</posx>
                <posy>0</posy>
                <control type="button" id="1032">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1026</onup>
                    <ondown>951</ondown>
                    <onright>1033</onright>
                    <onleft>1031</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>5[B][/B]</label>
                </control>
            </control>
            <control type="group">
                <posx>154</posx>
                <posy>0</posy>
                <control type="button" id="1033">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1027</onup>
                    <ondown>952</ondown>
                    <onright>1034</onright>
                    <onleft>1032</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>6[B][/B]</label>
                </control>
            </control>
            <control type="group">
                <posx>231</posx>
                <posy>0</posy>
                <control type="button" id="1034">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1028</onup>
                    <ondown>952</ondown>
                    <onright>1035</onright>
                    <onleft>1033</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>7[B][/B]</label>
                </control>
            </control>
            <control type="group">
                <posx>308</posx>
                <posy>0</posy>
                <control type="button" id="1035">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1029</onup>
                    <ondown>953</ondown>
                    <onright>1036</onright>
                    <onleft>1034</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>8[B][/B]</label>
                </control>
            </control>
            <control type="group">
                <posx>385</posx>
                <posy>0</posy>
                <control type="button" id="1036">
                    <animation effect="zoom" start="100" end="120" time="100" center="37,{{ vscale(37) }}" reversible="false">Focus</animation>
                    <animation effect="zoom" start="120" end="100" time="100" center="37,{{ vscale(37) }}" reversible="false">UnFocus</animation>
                    <hitrect x="0" y="0" w="75" h="75" />
                    <posx>-40</posx>
                    <posy>{{ vscale(-40) }}</posy>
                    <width>154</width>
                    <height>{{ vscale(154) }}</height>
                    <onup>1030</onup>
                    <ondown>953</ondown>
                    <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
                    <onleft>1035</onleft>
                    <font>font12</font>
                    <align>center</align>
                    <aligny>center</aligny>
                    <focusedcolor>FF000000</focusedcolor>
                    <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                    <texturenofocus>-</texturenofocus>
                    <label>9[B][/B]</label>
                </control>
            </control>
        </control>
    </control>

    <!-- DELETE-ETC -->
    <control type="group" id="950">
        <posx>60</posx>
        <posy>{{ vscale(840) }}</posy>
        <width>459</width>
        <height>{{ vscale(60) }}</height>
        <visible>String.IsEmpty(Window.Property(hide.kbd))</visible>
        <control type="image">
            <posx>0</posx>
            <posy>0</posy>
            <width>151</width>
            <height>{{ vscale(60) }}</height>
            <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
        </control>
        <control type="image">
            <posx>154</posx>
            <posy>0</posy>
            <width>151</width>
            <height>{{ vscale(60) }}</height>
            <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
        </control>
        <control type="image">
            <posx>308</posx>
            <posy>0</posy>
            <width>151</width>
            <height>{{ vscale(60) }}</height>
            <texture colordiffuse="FF000000">script.plex/white-square.png</texture>
        </control>

        <control type="group">
            <posx>0</posx>
            <posy>0</posy>
            <control type="button" id="951">
                <animation effect="zoom" start="100" end="120" time="100" center="75.5,{{ vscale(30) }}" reversible="false">Focus</animation>
                <animation effect="zoom" start="120" end="100" time="100" center="75.5,{{ vscale(30) }}" reversible="false">UnFocus</animation>
                <hitrect x="0" y="0" w="151" h="60" />
                <posx>-40</posx>
                <posy>{{ vscale(-40) }}</posy>
                <width>231</width>
                <height>{{ vscale(140) }}</height>
                <onleft>953</onleft>
                <onright>952</onright>
                <onup>1031</onup>
                <font>font12</font>
                <align>center</align>
                <aligny>center</aligny>
                <focusedcolor>FF000000</focusedcolor>
                <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                <texturenofocus>-</texturenofocus>
                <label>$ADDON[script.plexmod 32322]</label>
            </control>
        </control>
        <control type="group">
            <posx>154</posx>
            <posy>0</posy>
            <control type="button" id="952">
                <animation effect="zoom" start="100" end="120" time="100" center="75.5,{{ vscale(30) }}" reversible="false">Focus</animation>
                <animation effect="zoom" start="120" end="100" time="100" center="75.5,{{ vscale(30) }}" reversible="false">UnFocus</animation>
                <hitrect x="0" y="0" w="151" h="60" />
                <posx>-40</posx>
                <posy>{{ vscale(-40) }}</posy>
                <width>231</width>
                <height>{{ vscale(140) }}</height>
                <onleft>951</onleft>
                <onright>953</onright>
                <onup>1033</onup>
                <font>font12</font>
                <align>center</align>
                <aligny>center</aligny>
                <focusedcolor>FF000000</focusedcolor>
                <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                <texturenofocus>-</texturenofocus>
                <label>$ADDON[script.plexmod 32432]</label>
            </control>
        </control>
        <control type="group">
            <posx>308</posx>
            <posy>0</posy>
            <control type="button" id="953">
                <animation effect="zoom" start="100" end="120" time="100" center="75.5,{{ vscale(30) }}" reversible="false">Focus</animation>
                <animation effect="zoom" start="120" end="100" time="100" center="75.5,{{ vscale(30) }}" reversible="false">UnFocus</animation>
                <hitrect x="0" y="0" w="151" h="60" />
                <posx>-40</posx>
                <posy>{{ vscale(-40) }}</posy>
                <width>231</width>
                <height>{{ vscale(140) }}</height>
                <onleft>952</onleft>
                <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
                <onup>1036</onup>
                <font>font12</font>
                <align>center</align>
                <aligny>center</aligny>
                <focusedcolor>FF000000</focusedcolor>
                <texturefocus colordiffuse="FFE5A00D" border="50">script.plex/white-square-rounded-with-shadow.png</texturefocus>
                <texturenofocus>-</texturenofocus>
                <label>$ADDON[script.plexmod 32433]</label>
            </control>
        </control>
    </control>

    <control type="group">
        <animation effect="fade" start="0" end="100" time="100" condition="!String.IsEmpty(Window.Property(searching))">Visible</animation>
        <visible>!String.IsEmpty(Window.Property(searching))</visible>
        <posx>0</posx>
        <posy>{{ vscale(993) }}</posy>
        <control type="label">
            <scroll>false</scroll>
            <posx>420</posx>
            <posy>0</posy>
            <width>434</width>
            <height>{{ vscale(39) }}</height>
            <font>font12</font>
            <align>right</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>[UPPERCASE]$ADDON[script.plexmod 32434][/UPPERCASE]</label>
        </control>
        <control type="group">
            <posx>480</posx>
            <posy>0</posy>
            <control type="image">
                <visible>!String.IsEmpty(Window.Property(searching))</visible>
                <animation effect="rotate" start="0" end="-36000" time="100000" center="19.5,{{ vscale(19.5) }}" reversible="false">Visible</animation>
                <posx>0</posx>
                <posy>0</posy>
                <width>39</width>
                <height>{{ vscale(39) }}</height>
                <texture colordiffuse="FFE5A00D">script.plex/indicators/spinner.png</texture>
            </control>
        </control>
    </control>
    <control type="group">
        <visible>!String.IsEmpty(Window.Property(no.results)) + String.IsEmpty(Window.Property(searching))</visible>
        <posx>0</posx>
        <posy>{{ vscale(993) }}</posy>
        <control type="label">
            <scroll>false</scroll>
            <posx>0</posx>
            <posy>0</posy>
            <width>564</width>
            <height>{{ vscale(39) }}</height>
            <font>font12</font>
            <align>center</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>[UPPERCASE]$ADDON[script.plexmod 32435][/UPPERCASE]</label>
        </control>
    </control>
</control>

<control type="grouplist" id="3000">
    <!-- First search hub: slide once focus passes it -->
    <animation type="Conditional" condition="Integer.IsGreater(Window.Property(hub.focus),0) + Control.IsVisible(2000)" reversible="true">
        <effect type="slide" end="0,{{ vscale(-420) }}" time="200" tween="quadratic" easing="out"/>
    </animation>

    {% for i in range(1, core.search_hub_count) %}
    <animation type="Conditional" condition="Integer.IsGreater(Window.Property(hub.focus),{{ i }}) + Control.IsVisible({{ i + 2000 }})" reversible="true">
        <effect type="slide" end="0,{{ vscale(-420) }}" time="200" tween="quadratic" easing="out"/>
    </animation>
    {% endfor %}

    <defaultcontrol always="true">2000</defaultcontrol>
    <posx>564</posx>
    <posy>{{ vscale(20) }}</posy>
    <width>2130</width>
    <height>{{ vscale(5540) }}</height>
    <itemgap>20</itemgap>
    <orientation>vertical</orientation>
    <usecontrolcoords>true</usecontrolcoords>
    <scrolltime tween="quadratic" easing="out">200</scrolltime>

{% for i in range(core.search_hub_count) %}
{% with hub_id = i + 2100 & group_id = i + 2000 %}
    <control type="group" id="{{ group_id }}">
        <defaultcontrol>{{ hub_id }}</defaultcontrol>
        <visible>Integer.IsGreater(Container({{ hub_id }}).NumItems,0) + String.IsEmpty(Window.Property(drawing))</visible>
        <width>1356</width>
        <height>{{ vscale(420) }}</height>
        <control type="label">
            <scroll>false</scroll>
            <posx>60</posx>
            <posy>0</posy>
            <width>1000</width>
            <height>{{ vscale(87) }}</height>
            <font>font12</font>
            <align>left</align>
            <aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor>
            <label>[UPPERCASE]$INFO[Window.Property(hub.{{ hub_id }})][/UPPERCASE]</label>
        </control>
        <control type="list" id="{{ hub_id }}">
            <posx>0</posx>
            <posy>{{ vscale(30) }}</posy>
            <width>1356</width>
            <height>{{ vscale(440) }}</height>
            <onleft>899</onleft>
            <ondown>{{ hub_id + 1 }}</ondown>
            <scrolltime>200</scrolltime>
            <orientation>horizontal</orientation>
            <preloaditems>4</preloaditems>
            {% include "includes/search_hub_poster.xml.tpl" %}
            {% include "includes/search_hub_square.xml.tpl" %}
            {% include "includes/search_hub_ar16x9.xml.tpl" %}
            {% include "includes/search_hub_circle.xml.tpl" %}
        </control>
    </control>
{% endwith %}
{% endfor %}

</control>

<!-- SEARCH HISTORY LIST -->
<control type="group">
    <posx>564</posx>
    <posy>0</posy>
    <visible>!String.IsEmpty(Window.Property(show.history))</visible>
    <control type="image">
        <posx>0</posx>
        <posy>0</posy>
        <width>700</width>
        <height>{{ vscale(1080) }}</height>
        <texture colordiffuse="FF2D2D2D">script.plex/white-square.png</texture>
    </control>
    <control type="label">
        <scroll>false</scroll>
        <posx>60</posx>
        <posy>{{ vscale(20) }}</posy>
        <width>600</width>
        <height>{{ vscale(55) }}</height>
        <font>font12</font>
        <align>left</align>
        <aligny>center</aligny>
        <textcolor>FFFFFFFF</textcolor>
        <label>[UPPERCASE]$ADDON[script.plexmod 35004][/UPPERCASE]</label>
    </control>
    <control type="list" id="2050">
        <posx>40</posx>
        <posy>{{ vscale(75) }}</posy>
        <width>600</width>
        <height>{{ vscale(900) }}</height>
        <orientation>vertical</orientation>
        <onleft>650</onleft>
        <onright condition="!String.IsEmpty(Window.Property(show.history))">2050</onright>
                    <onright condition="String.IsEmpty(Window.Property(show.history))">3000</onright>
        <scrolltime>200</scrolltime>
        <itemlayout width="580" height="{{ vscale(50) }}">
            <control type="image">
                <posx>20</posx>
                <posy>{{ vscale(13) }}</posy>
                <width>24</width>
                <height>{{ vscale(24) }}</height>
                <texture colordiffuse="99FFFFFF">$INFO[ListItem.Property(icon)]</texture>
            </control>
            <control type="label">
                <posx>60</posx>
                <posy>0</posy>
                <width>500</width>
                <height>{{ vscale(50) }}</height>
                <font>font13</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>CCFFFFFF</textcolor>
                <label>$INFO[ListItem.Label]</label>
            </control>
        </itemlayout>
        <focusedlayout width="580" height="{{ vscale(50) }}">
            <control type="image">
                <posx>0</posx>
                <posy>0</posy>
                <width>580</width>
                <height>{{ vscale(50) }}</height>
                <texture border="10">script.plex/home/selected.png</texture>
            </control>
            <control type="image">
                <posx>20</posx>
                <posy>{{ vscale(13) }}</posy>
                <width>24</width>
                <height>{{ vscale(24) }}</height>
                <texture colordiffuse="FFFFFFFF">$INFO[ListItem.Property(icon)]</texture>
            </control>
            <control type="label">
                <posx>60</posx>
                <posy>0</posy>
                <width>500</width>
                <height>{{ vscale(50) }}</height>
                <font>font13</font>
                <align>left</align>
                <aligny>center</aligny>
                <textcolor>FFFFFFFF</textcolor>
                <label>$INFO[ListItem.Label]</label>
            </control>
        </focusedlayout>
    </control>
</control>
{% endblock controls %}