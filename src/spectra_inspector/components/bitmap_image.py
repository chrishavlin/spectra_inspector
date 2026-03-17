
from dash import html, dcc
from dash_bootstrap_components import Button


class bitmapImageLayoutIDs:
    id_type_base: str

    def __init__(self, id_type_base: str = 'bitmap-image') -> None:
        self.id_type_base = id_type_base

    @property
    def div(self) -> str: 
        return self.full_id('-div')
    
    @property
    def graph(self) -> str: 
        return self.full_id('-graph')
    
    @property
    def slider(self) -> str: 
        return self.full_id('-slider')
    
    @property
    def refresh(self) -> str: 
        return self.full_id('-refresh')
    
    @property
    def delete(self) -> str: 
        return self.full_id('-delete')
    
    def full_id(self, id_suffix:str) -> str:
        return self.id_type_base + id_suffix


def bitmap_image_layout(index: int,
                        id_type_base: str = 'bitmap-image',
                        slider_bg_hexcolor:str = '#FFFFFF', 
                        button_label:str = "Refresh Image",
                        delete_button_label:str = "Delete Image",
                        slider_start: float = 0.0, 
                        slider_stop: float = 15.0, 
                        slider_init_range: tuple[float, float] = (1.65, 1.9),
                        slider_step: float = 0.1)-> tuple[html.Div, bitmapImageLayoutIDs]:

    imIDs = bitmapImageLayoutIDs(id_type_base=id_type_base)
    
    fig_image = dcc.Graph(id={'type': imIDs.graph, 
                              'index': index})

    energy_range = dcc.RangeSlider(slider_start, 
                                   slider_stop, 
                                   step=slider_step, 
                                   value=slider_init_range, 
                                   id={'type': imIDs.slider, 
                                       'index': index}, 
                                   className="text-info")

    _primary_graph_div = html.Div([
        html.Div(energy_range, style={'background': slider_bg_hexcolor}),
        Button(button_label, id={'type': imIDs.refresh, 'index': index}),
        Button(delete_button_label, id={'type': imIDs.delete, 'index': index}),
        fig_image,

    ], id={'type': imIDs.div, 
            'index': index})

    return _primary_graph_div, imIDs