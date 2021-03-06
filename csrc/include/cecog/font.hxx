/*******************************************************************************

                           The CellCognition Project
                   Copyright (c) 2006 - 2010 by Michael Held
                      Gerlich Lab, ETH Zurich, Switzerland
                             www.cellcognition.org

              CellCognition is distributed under the LGPL License.
                        See trunk/LICENSE.txt for details.
                 See trunk/AUTHORS.txt for author contributions.

*******************************************************************************/

// Author(s): Michael Held
// $Date$
// $Rev$
// $URL$


#ifndef CECOG_FONT
#define CECOG_FONT

#include <map>
#include <string>

#include "vigra/impex.hxx"
#include "vigra/stdimage.hxx"
#include "vigra/transformimage.hxx"
#include "vigra/copyimage.hxx"


namespace cecog
{

  class Font
  {
  public:
    Font(std::string const & filename, int correct=3, int tiles=16)
      : tiles(tiles), correct(correct)
    {
      struct stat buffer;
      if(stat (filename.c_str(), &buffer) > 0 ) {
        vigra::ImageImportInfo info(filename.c_str());
        width = info.width();
        height = info.height();
        charw = width / tiles;
        charh = height / tiles;
        img = vigra::BImage(width, height);
        importImage(info, destImage(img));
      }
      else {
        // This is a dummy image (empty) in the absence of a font-image
        // This modification makes it possible to call the cellcognition
        // from any directory (without the pipeline, and on a single image)
        width = 256;
        height = 256;
        charw = width / tiles;
        charh = height / tiles;
        img = vigra::BImage(width, height);
      }

    }

    template <class VALUETYPE>
    void write(vigra::BasicImage<VALUETYPE> & dest,
               Point p,
               std::string const & text)
    {
      // due to seg faults writing over the image borders,
      // we MUST check if the line or character is still inside:
      // line inside? check y-values
      if (p.y+charh < dest.height()-1)
      {
        typename vigra::BasicImage<VALUETYPE>::traverser
        dest_i(dest.upperLeft() + p);

        // char inside? check x-values
        for (std::string::size_type i = 0; i < text.size() &&
               dest_i.x+charw < dest.width()-1; ++i) {
          unsigned char letter = text[i];
          int cx = (letter % tiles) * charw;
          int cy = (letter / tiles) * charh;
          vigra::Diff2D ul(cx, cy);
          vigra::Diff2D lr = ul + vigra::Diff2D(charw, charh);
          copyImageIf(img.upperLeft()+ul,
                      img.upperLeft()+lr, img.accessor(),
                      img.upperLeft()+ul, img.accessor(),
                      dest_i,
                      dest.accessor());
          dest_i.x += charw - correct;
        }
      }
    }

  private:
    vigra::BImage img;
    int tiles, correct, width, height, charw, charh;
  };

}

#endif // CECOG_FONT
